from app.models.asset import Asset, AssetFile
from app.models.folder import Folder
from app.models.job import Job, JobOutput
from app.models.setting import Setting
from app.models.workflow import RegisteredWorkflow

__all__ = [
    "Setting",
    "Folder",
    "Asset",
    "AssetFile",
    "Job",
    "JobOutput",
    "RegisteredWorkflow",
]

KIND_CHARACTER = "character"
KIND_SCENE = "scene"
ASSET_KINDS = (KIND_CHARACTER, KIND_SCENE)
