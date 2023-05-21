import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from numpy.typing import NDArray

from .._version import __version__
from ..detect_cameras import CalibratedCamera, find_cameras
from ..frame_sources import USBCamera
from ..helpers.markers import generate_marker_size_mapping
from ..helpers.sender import Base64Sender
from ..marker import Marker
from ..utils import Frame
from ..vision import Processor

LOGGER = logging.getLogger(__name__)


class AprilCamera:
    """
    Virtual Camera Board for detecting fiducial markers.

    Additionally, it will do pose estimation, along with some calibration
    in order to determine the spatial positon and orientation of the markers
    that it has detected.
    """

    name: str = "AprilTag Camera Board"

    @classmethod
    def discover(cls) -> Dict[str, 'AprilCamera']:
        """Discover boards that this backend can control."""
        return {
            (serial := f"{camera_data.name} - {camera_data.index}"):
            cls(camera_data.index, camera_data=camera_data, serial_num=serial)
            for camera_data in find_cameras(
                os.environ.get('OPENCV_CALIBRATIONS', '.').split(':'))
        }

    def __init__(self, camera_id: int, camera_data: CalibratedCamera, serial_num: str) -> None:
        """Generate a backend from the camera index and calibration data."""
        camera_source = USBCamera.from_calibration_file(
            camera_id,
            calibration_file=camera_data.calibration,
            vidpid=camera_data.vidpid,
        )
        self._cam = Processor(
            camera_source,
            calibration=camera_source.calibration,
            name=camera_data.name,
            vidpid=camera_data.vidpid,
            mask_unknown_size_tags=True,
        )
        self._serial = serial_num

    @property
    def serial_number(self) -> str:
        """Get the serial number."""
        return self._serial

    @property
    def firmware_version(self) -> Optional[str]:
        """Get the firmware version of the board."""
        return f"April camera v{__version__}"

    def make_safe(self) -> None:
        """
        Close the camera.

        The camera will no longer work after this method is called.
        """
        self._cam.close()

    # Proxy methods from USBCamera object
    def see(self, *, eager: bool = True, frame: Optional[NDArray] = None) -> List[Marker]:
        """
        Capture an image and identify fiducial markers.

        :param eager: Process the pose estimations of markers immediately,
            currently unused.
        :returns: list of markers that the camera could see.
        """
        return self._cam.see(frame=frame)

    def capture(self) -> NDArray:
        """
        Get the raw image data from the camera.

        :returns: Camera pixel data
        """
        return self._cam.capture()

    def save(self, path: Union[Path, str], *, frame: Optional[NDArray] = None) -> None:
        """Save an annotated image to a path."""
        self._cam.save(path, frame=frame)

    def set_marker_sizes(
        self,
        tag_sizes: Union[float, Dict[int, float]],
    ) -> None:
        self._cam.set_marker_sizes(tag_sizes)

    def set_detection_hook(self, callback: Callable[[Frame, List[Marker]], None]):
        self._cam.detection_hook = callback


def setup_cameras(
    tag_sizes: Union[float, Dict[int, float]],
    publish_func: Optional[Callable[[str, bytes], None]] = None,
) -> Dict[str, AprilCamera]:
    expanded_tag_sizes = generate_marker_size_mapping(tag_sizes)

    if publish_func:
        frame_sender = Base64Sender(publish_func)

    cameras = AprilCamera.discover()

    for camera in cameras.values():
        camera.set_marker_sizes(expanded_tag_sizes)
        if publish_func:
            camera.set_detection_hook(frame_sender.annotated_frame_hook)

    return cameras
