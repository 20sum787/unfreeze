#pragma once

// Shared deployment settings included by config.h. After editing, run
// python3 tools/sync_config.py --write before importing or rebuilding the app.
// The camera service name and port must match Arduino's video_object_detection brick.
#define UF_COMPANION_HOST "0.0.0.0"
#define UF_COMPANION_PORT 7000
#define UF_CAMERA_HOST "ei-video-obj-detection-runner"
#define UF_CAMERA_PORT 4912
#define UF_BRIDGE_TIMEOUT_MS 600
#define UF_DOOR_CONFIDENCE 0.50
#define UF_MOTION_CONFIDENCE 0.75
