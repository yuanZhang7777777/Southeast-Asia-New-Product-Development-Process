import os


# Tests must never inherit a developer machine's production OSS upload switch.
os.environ["OSS_UPLOAD_ENABLED"] = "false"
