"""
scripts/time_base.py
Defines the conversion between Video 5 MP4 playback time and real wall-clock time.

Background:
vial_fill_video_5.mp4 has a container framerate of 30.0 fps, but was recorded
at ~24.676 fps in hardware (confirmed via 10 burned-in clock readings across the video).
Thus, MP4 playback runs ~1.2158x faster than real wall-clock time.

Constants:
- SLOPE: 1.215771 (real_seconds = SLOPE * mp4_seconds)
- MP4_T0_DATETIME: 2026-09-23 19:47:10.547000 (burned-in clock at mp4_s = 0.0)
"""

from datetime import datetime, timedelta
from typing import Union

# Fitted constants
SLOPE = 1.215771
INTERCEPT = 0.000027
MP4_T0_DATETIME = datetime(2026, 9, 23, 19, 47, 10, 547000)
MP4_T0_CLOCK_STR = "19:47:10.547"


def mp4_to_real(mp4_s: float, as_datetime: bool = False) -> Union[float, datetime]:
    """
    Converts MP4 playback seconds to real time.
    
    Args:
        mp4_s: Elapsed seconds in MP4 video playback (at 30.0 fps).
        as_datetime: If True, returns wall-clock datetime object.
                     If False, returns real elapsed seconds from video t=0.
    """
    real_elapsed_s = SLOPE * mp4_s + INTERCEPT
    if as_datetime:
        return MP4_T0_DATETIME + timedelta(seconds=real_elapsed_s)
    return real_elapsed_s


def real_to_mp4(real_val: Union[float, datetime]) -> float:
    """
    Converts real wall-clock time to MP4 playback seconds.
    
    Args:
        real_val: Either real elapsed seconds from video t=0, or a wall-clock datetime object.
        
    Returns:
        float: MP4 playback seconds (at 30.0 fps).
    """
    if isinstance(real_val, datetime):
        real_elapsed_s = (real_val - MP4_T0_DATETIME).total_seconds()
    else:
        real_elapsed_s = float(real_val)
    return (real_elapsed_s - INTERCEPT) / SLOPE


if __name__ == "__main__":
    print(f"Time Base Constants:")
    print(f"  SLOPE: {SLOPE}")
    print(f"  MP4 t=0 Clock: {MP4_T0_DATETIME.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    test_mp4_s = 100.0
    real_s = mp4_to_real(test_mp4_s)
    real_dt = mp4_to_real(test_mp4_s, as_datetime=True)
    back_mp4 = real_to_mp4(real_s)
    back_mp4_dt = real_to_mp4(real_dt)
    print(f"\nVerification test for mp4_s = {test_mp4_s}:")
    print(f"  real elapsed s: {real_s:.4f} s")
    print(f"  real datetime:  {real_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"  back from s:    {back_mp4:.4f} s")
    print(f"  back from dt:   {back_mp4_dt:.4f} s")
