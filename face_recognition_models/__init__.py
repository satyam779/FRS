"""Local model path helpers for face_recognition."""

from pathlib import Path

__author__ = "Adam Geitgey"
__email__ = "ageitgey@gmail.com"
__version__ = "0.1.0"

_MODELS_DIR = Path(__file__).resolve().parent / "models"


def _model_path(filename):
    return str((_MODELS_DIR / filename).resolve())


def pose_predictor_model_location():
    return _model_path("shape_predictor_68_face_landmarks.dat")


def pose_predictor_five_point_model_location():
    return _model_path("shape_predictor_5_face_landmarks.dat")


def face_recognition_model_location():
    return _model_path("dlib_face_recognition_resnet_model_v1.dat")


def cnn_face_detector_model_location():
    return _model_path("mmod_human_face_detector.dat")
