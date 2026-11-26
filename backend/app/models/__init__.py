from app.models.asset import Asset, AssetFile
from app.models.folder import Folder
from app.models.setting import Setting

__all__ = ["Setting", "Folder", "Asset", "AssetFile"]

KIND_CHARACTER = "character"
KIND_SCENE = "scene"
ASSET_KINDS = (KIND_CHARACTER, KIND_SCENE)
