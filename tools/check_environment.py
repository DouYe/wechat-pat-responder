import platform
import sys


def fail(message):
    print(f"ERROR: {message}")
    raise SystemExit(1)


if platform.system() != "Windows":
    fail("Windows 10 or Windows 11 is required.")
if sys.maxsize <= 2**32:
    fail("64-bit Python is required.")
if sys.version_info < (3, 10):
    fail("Python 3.10 or newer is required.")

try:
    import PIL
    import win32gui
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine
except Exception as exc:
    fail(f"A required package could not be imported: {exc}")

engine = OcrEngine.try_create_from_language(Language("en-US"))
if engine is None:
    engine = OcrEngine.try_create_from_user_profile_languages()
if engine is None:
    fail("No Windows OCR engine is installed.")

print(f"Windows: {platform.version()}")
print(f"Python: {platform.python_version()} ({platform.machine()})")
print(f"Pillow: {PIL.__version__}")
print(f"OCR language: {engine.recognizer_language.language_tag}")
print("Environment check passed.")
