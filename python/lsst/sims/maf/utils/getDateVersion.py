import os
import time

__all__ = ['getDateVersion']


def getDateVersion():
    """
    Get today's date and a dictionary with the MAF version information.
    This is written into configuration output files, to help track MAF runs.

    Returns
    -------
    str, dict
        String with today's date, Dictionary with version information.
    """
    import lsst.sims.maf

    version = lsst.sims.maf.version
    today_date = time.strftime("%x")
    versionInfo = {'__version__': version.__version__,
                   '__repo_version__': version.__repo_version__,
                   '__fingerprint__': version.__fingerprint__,
                   '__dependency_versions__': version.__dependency_versions__}

    return today_date, versionInfo
