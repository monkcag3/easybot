
import asyncio
import os
import argparse
import sys
from pathlib import Path
from pathlib import Path
from dotenv import load_dotenv
import zmq
from zmq.asyncio import Context, Poller
import numpy as np
import sounddevice as sd
import sherpa_onnx

__stoped__ = False

def assert_file_exists(
    filename: str,
    message: str,
) -> None:
    if not filename:
        raise ValueError(f"Please specify {message}")
    if not Path(filename).is_file():
        raise ValueError(f"{message} {filename} does not exist")

def check_first_pass_args():
    assert_file_exists(os.getenv("first-tokens"), "--first-tokens")
    assert_file_exists(os.getenv("first-encoder"), "--first-encoder")
    assert_file_exists(os.getenv("first-decoder"), "--first-decoder")
    assert_file_exists(os.getenv("first-joiner"), "--first-joiner")

def check_second_pass_args():
    assert_file_exists(os.getenv("second-tokens"), "--second-tokens")
    assert_file_exists(os.getenv("second-paraformer"), "--second-paraformer")

def load_env_config():
    env_path = Path(".") / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path = env_path)
        print(f"✅ 已加载配置文件: {env_path.absolute()}")
    else:
        print(f"⚠️ 未找到.env文件，使用默认值或命令行参数")

def load_env():
    load_env_config()
    check_first_pass_args()
    check_second_pass_args()

def create_first_pass_recognizer():
    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens = os.getenv("first-tokens"),
        encoder = os.getenv("first-encoder"),
        decoder = os.getenv("first-decoder"),
        joiner = os.getenv("first-joiner"),
        num_threads = 1,
        sample_rate = 16000,
        feature_dim = 80,
        decoding_method = os.getenv("first-decoding-method")
        max_active_paths = int(os.getenv("first-max-active-paths")),
        provider = os.getenv("provider"),
        enable_endpoint_detection = True,
        rule1_min_trailing_silence = 2.4,
        rule2_min_trailing_silence = 1.2,
        rule3_min_utterance_length = 20,
    )
    return recognizer

def create_second_pass_recognizer(
) -> sherpa_onnx.OfflineRecognizer:
    if os.getenv("second-encoder"):
        recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            encoder = os.getenv("second-encoder"),
            decoder = os.getenv("second-decoder"),
            joiner = os.getenv("second-joiner"),
            tokens = os.getenv("second-tokens"),
            sample_rate = 16000,
            feature_dim = 80,
            decoding_method = "greedy_search",
            max_active_paths = 4,
        )
    elif os.getenv("second-paraformer"):
        recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer = os.getenv("second-paraformer"),
            tokens = os.getenv("second-tokens"),
            num_threads = 1,
            sample_rate = 16000,
            feature_dim = 80,
            decoding_method = "greedy_search",
        )
    elif os.getenv("second-nemo-ctc"):
        recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model = os.getenv("second-nemo-ctc"),
            tokens = os.getenv("second-tokens"),
            num_threads = 1,
            sample_rate = 16000,
            feature_dim = 80,
            decoding_method = "greedy_search",
        )
    elif os.getenv("second-whisper-encoder"):
        recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder = os.getenv("second-whisper-encoder"),
            decoder = os.getenv("second-whisper-decoder"),
            tokens = os.getenv("second-tokens"),
            num_threads = 1,
            decoding_method = "greedy_search",
            language = os.getenv("second-whisper-language"),
            task = os.getenv("second-whisper-task"),
            tail_paddings = os.getenv("second-whisper-tail-paddings"),
        )
    else:
        raise ValueError("Please specify at least one model for the second pass")
    return recognizer

def run_second_pass(
    recognizer: sherpa_onnx.OfflineRecognizer,
    samples: np.ndarray,
    sample_rate: int,
) -> None:
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)
    return stream.result.text

async def run():
    devices = sd.query_devices()
    if len(devices) == 0:
        print("No microphone devices found")
        sys.exit(0)

    default_input_device_idx = sd.default.device[0]
    first_recognizer = create_first_pass_recognizer()
    second_recognizer = create_second_pass_recognizer()

    sample_rate = 16000
    samples_per_read = int(1.0 * sample_rate)
    stream = first_recognizer.create_stream()

    ctx = Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.connect("inproc://easybot.ai/rx/audio")

    pre_result = ""
    sample_buffers = []
    with sd.InputStream(device=2, channels=1, dtype="float32", samplerate=sample_rate) as s:
        while True:
            if __stoped__:
                break
            samples, _ = s.read(samples_per_read)
            samples = samples.reshape(-1)
            stream.accept_waveform(sample_rate, samples)

            sample_buffers.append(samples)

            while first_recognizer.is_ready(stream):
                first_recognizer.decode_stream(stream)

            is_endpoint = first_recognizer.is_endpoint(stream)
            result = first_recognizer.get_result(stream)
            result = result.lower().strip()

            ## 增量发送数据
            if result != "":
                increase_result = result[len(pre_result):]
                if increase_result:
                    await pub.send_multipart([b"audio-text", increase_result.encode()])
                pre_result = result
            ## 让出协程资源，否则会一直在这个循环里，阻塞了其他协程
            await asyncio.sleep(0.01)

            ## 第二阶段处理："完整"分段处理
            if is_endpoint:
                pre_result = ""
                if result:
                    samples = np.concatenate(sample_buffers)
                    sample_buffers = [samples[-8000:]]
                    samples = samples[:-8000]
                    result = run_second_pass(
                        recognizer = second_recognizer,
                        samples = samples,
                        sample_rate = sample_rate,
                    )
                    result = result.lower().strip()
                    ## todo: 发送第二阶段数据
                else:
                    sample_buffers = []
                first_recognizer.reset(stream)

def shutdown():
    __stoped__ = True
