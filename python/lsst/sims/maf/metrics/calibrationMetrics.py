import numpy as np
from .baseMetric import BaseMetric
import lsst.sims.maf.utils as mafUtils
from scipy.stats import spearmanr

__all__ = ['ParallaxMetric', 'ProperMotionMetric', 'RadiusObsMetric',
           'ParallaxCoverageMetric', 'ParallaxHADegenMetric']


class ParallaxMetric(BaseMetric):
    """Calculate the uncertainty in a parallax measures given a serries of observations.
    """

    def __init__(self, metricName='parallax', m5Col='fiveSigmaDepth',
                 mjdCol='expMJD', units = 'mas',
                 filterCol='filter', seeingCol='FWHMgeom', rmag=20.,
                 SedTemplate='flat', badval=-666,
                 atm_err=0.01, normalize=False, **kwargs):
        """ Instantiate metric.

        m5Col = column name for inidivual visit m5
        mjdCol = column name for exposure time dates
        filterCol = column name for filter
        seeingCol = column name for seeing/FWHMgeom
        rmag = mag of fiducial star in r filter.  Other filters are scaled using sedTemplate keyword
        SedTemplate = string of 'flat' or 'O','B','A','F','G','K','M'.
        atm_err = centroiding error due to atmosphere in arcsec
        normalize = Compare to a survey that has all observations with maximum parallax factor.
        An optimally scheduled survey would be expected to have a normalized value close to unity,
        and zero for a survey where the parallax can not be measured.

        return uncertainty in mas. Or normalized map as a fraction
        """
        Cols = [m5Col, mjdCol, filterCol, seeingCol, 'ra_pi_amp', 'dec_pi_amp']
        if normalize:
            units = 'ratio'
        super(ParallaxMetric, self).__init__(Cols, metricName=metricName, units=units,
                                             badval=badval, **kwargs)
        # set return type
        self.m5Col = m5Col
        self.seeingCol = seeingCol
        self.filterCol = filterCol
        filters = ['u', 'g', 'r', 'i', 'z', 'y']
        self.mags = {}
        if SedTemplate == 'flat':
            for f in filters:
                self.mags[f] = rmag
        else:
            self.mags = mafUtils.stellarMags(SedTemplate, rmag=rmag)
        self.atm_err = atm_err
        self.normalize = normalize
        self.comment = 'Estimated uncertainty in parallax measurement (assuming no proper motion or that proper motion '
        self.comment += 'is well fit). Uses measurements in all bandpasses, and estimates astrometric error based on SNR '
        self.comment += 'in each visit. '
        if SedTemplate == 'flat':
            self.comment += 'Assumes a flat SED. '
        if self.normalize:
            self.comment += 'This normalized version of the metric displays the estimated uncertainty in the parallax measurement, '
            self.comment += 'divided by the minimum parallax uncertainty possible (if all visits were six '
            self.comment += 'months apart). Values closer to 1 indicate more optimal scheduling for parallax measurement.'

    def _final_sigma(self, position_errors, ra_pi_amp, dec_pi_amp):
        """Assume parallax in RA and DEC are fit independently, then combined.
        All inputs assumed to be arcsec """
        sigma_A = position_errors/ra_pi_amp
        sigma_B = position_errors/dec_pi_amp
        sigma_ra = np.sqrt(1./np.sum(1./sigma_A**2))
        sigma_dec = np.sqrt(1./np.sum(1./sigma_B**2))
        # combine RA and Dec uncertainties, convert to mas
        sigma = np.sqrt(1./(1./sigma_ra**2+1./sigma_dec**2))*1e3
        return sigma

    def run(self, dataslice, slicePoint=None):
        filters = np.unique(dataslice[self.filterCol])
        snr = np.zeros(len(dataslice), dtype='float')
        # compute SNR for all observations
        for filt in filters:
            good = np.where(dataslice[self.filterCol] == filt)
            snr[good] = mafUtils.m52snr(self.mags[filt], dataslice[self.m5Col][good])
        position_errors = np.sqrt(mafUtils.astrom_precision(
            dataslice[self.seeingCol], snr)**2+self.atm_err**2)
        sigma = self._final_sigma(position_errors, dataslice['ra_pi_amp'], dataslice['dec_pi_amp'])
        if self.normalize:
            # Leave the dec parallax as zero since one can't have ra and dec maximized at the same time.
            sigma = self._final_sigma(position_errors, dataslice[
                                      'ra_pi_amp']*0+1., dataslice['dec_pi_amp']*0)/sigma
        return sigma


class ProperMotionMetric(BaseMetric):
    """Calculate the uncertainty in the returned proper motion.  Assuming Gaussian errors.
    """

    def __init__(self, metricName='properMotion',
                 m5Col='fiveSigmaDepth', mjdCol='expMJD', units='mas/yr',
                 filterCol='filter', seeingCol='FWHMgeom', rmag=20.,
                 SedTemplate='flat', badval= -666,
                 atm_err=0.01, normalize=False,
                 baseline=10., **kwargs):
        """ Instantiate metric.

        m5Col = column name for inidivual visit m5
        mjdCol = column name for exposure time dates
        filterCol = column name for filter
        seeingCol = column name for seeing (assumed FWHM)
        rmag = mag of fiducial star in r filter.  Other filters are scaled using sedTemplate keyword
        sedTemplate = template to use (can be 'flat' or 'O','B','A','F','G','K','M')
        atm_err = centroiding error due to atmosphere in arcsec
        normalize = Compare to the uncertainty that would result if half
        the observations were taken at the start of the survey and half
        at the end.  A 'perfect' survey will have a value close to unity,
        while a poorly scheduled survey will be close to zero.
        baseline = The length of the survey used for the normalization (years)
        """
        cols = [m5Col, mjdCol, filterCol, seeingCol]
        if normalize:
            units = 'ratio'
        super(ProperMotionMetric, self).__init__(col=cols, metricName=metricName, units=units,
                                                 badval=badval, **kwargs)
        # set return type
        self.seeingCol = seeingCol
        self.m5Col = m5Col
        filters = ['u', 'g', 'r', 'i', 'z', 'y']
        self.mags = {}
        if SedTemplate == 'flat':
            for f in filters:
                self.mags[f] = rmag
        else:
            self.mags = mafUtils.stellarMags(SedTemplate, rmag=rmag)
        self.atm_err = atm_err
        self.normalize = normalize
        self.baseline = baseline
        self.comment = 'Estimated uncertainty of the proper motion fit (assuming no parallax or that parallax is well fit). '
        self.comment += 'Uses visits in all bands, and generates approximate astrometric errors using the SNR in each visit. '
        if SedTemplate == 'flat':
            self.comment += 'Assumes a flat SED. '
        if self.normalize:
            self.comment += 'This normalized version of the metric represents the estimated uncertainty in the proper '
            self.comment += 'motion divided by the minimum uncertainty possible (if all visits were '
            self.comment += 'obtained on the first and last days of the survey). Values closer to 1 '
            self.comment += 'indicate more optimal scheduling.'

    def run(self, dataslice, slicePoint=None):
        filters = np.unique(dataslice['filter'])
        precis = np.zeros(dataslice.size, dtype='float')
        for f in filters:
            observations = np.where(dataslice['filter'] == f)
            if np.size(observations[0]) < 2:
                precis[observations] = self.badval
            else:
                snr = mafUtils.m52snr(self.mags[f],
                                      dataslice[self.m5Col][observations])
                precis[observations] = mafUtils.astrom_precision(
                    dataslice[self.seeingCol][observations], snr)
                precis[observations] = np.sqrt(precis[observations]**2 + self.atm_err**2)
        good = np.where(precis != self.badval)
        result = mafUtils.sigma_slope(dataslice['expMJD'][good], precis[good])
        result = result*365.25*1e3  # convert to mas/yr
        if (self.normalize) & (good[0].size > 0):
            new_dates = dataslice['expMJD'][good]*0
            nDates = new_dates.size
            new_dates[nDates/2:] = self.baseline*365.25
            result = (mafUtils.sigma_slope(new_dates, precis[good])*365.25*1e3)/result
        # Observations that are very close together can still fail
        if np.isnan(result):
            result = self.badval
        return result


class ParallaxCoverageMetric(BaseMetric):
    """
    Check how well the parallax factor is distributed. Subtracts the weighted mean position of the
    parallax offsets, then computes the weighted mean radius of the points.
    If points are well distributed, the mean radius will be near 1. If phase coverage is bad,
    radius will be close to zero.

    For points on the Ecliptic, uniform sampling should result in a metric value of ~0.5.
    At the poles, uniform sampling would result in a metric value of ~1.
    Conceptually, it is helpful to remember that the parallax motion of a star at the pole is
    a (nearly circular) ellipse while the motion of a star on the ecliptic is a straight line. Thus, any
    pair of observations seperated by 6 months will give the full parallax range for a star on the pole
    but only observations on very spefic dates will give the full range for a star on the ecliptic.

    Optionally also demand that there are obsevations above the snrLimit kwarg spanning thetaRange radians.
    """

    def __init__(self, metricName='ParallaxCoverageMetric', m5Col='fiveSigmaDepth',
                 mjdCol='expMJD', filterCol='filter', seeingCol='FWHMgeom',
                 rmag=20., SedTemplate='flat', badval=-666,
                 atm_err=0.01, thetaRange=0., snrLimit=5, **kwargs):
        """
        instantiate metric

        m5Col = column name for inidivual visit m5
        mjdCol = column name for exposure time dates
        filterCol = column name for filter
        seeingCol = column name for seeing (assumed FWHM)
        rmag = mag of fiducial star in r filter.  Other filters are scaled using sedTemplate keyword
        sedTemplate = template to use (can be 'flat' or 'O','B','A','F','G','K','M')
        atm_err = centroiding error due to atmosphere in arcsec
        thetaRange = range of parallax offset angles to demand (in radians) default=0 means no range requirement
        snrLimit = only include points above the snrLimit (default 5) when computing thetaRange.
        """

        cols = ['ra_pi_amp', 'dec_pi_amp', m5Col, mjdCol, filterCol, seeingCol]
        units = 'ratio'
        super(ParallaxCoverageMetric, self).__init__(cols,
                                                     metricName=metricName, units=units,
                                                     **kwargs)
        self.m5Col = m5Col
        self.seeingCol = seeingCol
        self.filterCol = filterCol
        self.mjdCol = mjdCol

        # Demand the range of theta values
        self.thetaRange = thetaRange
        self.snrLimit = snrLimit

        filters = ['u', 'g', 'r', 'i', 'z', 'y']
        self.mags = {}
        if SedTemplate == 'flat':
            for f in filters:
                self.mags[f] = rmag
        else:
            self.mags = mafUtils.stellarMags(SedTemplate, rmag=rmag)
        self.atm_err = atm_err

    def _thetaCheck(self, ra_pi_amp, dec_pi_amp, snr):
        good = np.where(snr >= self.snrLimit)
        theta = np.arctan2(dec_pi_amp[good], ra_pi_amp[good])
        # Make values between 0 and 2pi
        theta = theta-np.min(theta)
        result = 0.
        if np.max(theta) >= self.thetaRange:
            # Check that things are in differnet quadrants
            theta = (theta+np.pi) % 2.*np.pi
            theta = theta-np.min(theta)
            if np.max(theta) >= self.thetaRange:
                result = 1
        return result

    def _computeWeights(self, dataSlice, snr):
        # Compute centroid uncertainty in each visit
        position_errors = np.sqrt(mafUtils.astrom_precision(
            dataSlice[self.seeingCol], snr)**2+self.atm_err**2)
        weights = 1./position_errors**2
        return weights

    def _weightedR(self, dec_pi_amp, ra_pi_amp, weights):
        ycoord = dec_pi_amp-np.average(dec_pi_amp, weights=weights)
        xcoord = ra_pi_amp-np.average(ra_pi_amp, weights=weights)
        radius = np.sqrt(xcoord**2+ycoord**2)
        aveRad = np.average(radius, weights=weights)
        return aveRad

    def run(self, dataSlice, slicePoint=None):

        if np.size(dataSlice) < 2:
            return self.badval

        filters = np.unique(dataSlice[self.filterCol])
        snr = np.zeros(len(dataSlice), dtype='float')
        # compute SNR for all observations
        for filt in filters:
            inFilt = np.where(dataSlice[self.filterCol] == filt)
            snr[inFilt] = mafUtils.m52snr(self.mags[filt], dataSlice[self.m5Col][inFilt])

        weights = self._computeWeights(dataSlice, snr)
        aveR = self._weightedR(dataSlice['ra_pi_amp'], dataSlice['dec_pi_amp'], weights)
        if self.thetaRange > 0:
            thetaCheck = self._thetaCheck(dataSlice['ra_pi_amp'], dataSlice['dec_pi_amp'], snr)
        else:
            thetaCheck = 1.
        result = aveR*thetaCheck
        return result


class ParallaxHADegenMetric(BaseMetric):
    """
    Check for degeneracy between parallax and DCR.  Value of zero means there is no correlation.
    Values of +/-1 mean correlation (or anti-correlation, which is probably just as bad). Uses
    Spearman R statistic to look for correlation.

    Note this is a conservative metric, as the parallax displacement and DCR displacement
    could be in different directions. This metric only looks at the magnitude of the parallax
    displacement and checks that it is not correlated with hour angle.
    """

    def __init__(self, metricName='ParallaxHADegenMetric', haCol='HA', snrLimit=5.,
                 m5Col='fiveSigmaDepth', mjdCol='expMJD',
                 filterCol='filter', seeingCol='FWHMgeom',
                 rmag=20., SedTemplate='flat', badval=-666,
                 **kwargs):
        """
        haCol = Hour angle column name
        snrLimit = only inlcude observations above the snrLimit
        m5Col = column name for inidivual visit m5
        mjdCol = column name for exposure time dates
        filterCol = column name for filter
        seeingCol = column name for seeing (assumed FWHM)
        rmag = mag of fiducial star in r filter.  Other filters are scaled using sedTemplate keyword
        sedTemplate = template to use (can be 'flat' or 'O','B','A','F','G','K','M')
        """

        cols = ['ra_pi_amp', 'dec_pi_amp']
        self.haCol = haCol
        cols.append(haCol)
        units = 'Correlation'
        self.snrLimit = snrLimit
        super(ParallaxHADegenMetric, self).__init__(cols,
                                                    metricName=metricName,
                                                    units=units, **kwargs)
        self.m5Col = m5Col
        self.seeingCol = seeingCol
        self.filterCol = filterCol
        self.mjdCol = mjdCol
        filters = ['u', 'g', 'r', 'i', 'z', 'y']
        self.mags = {}
        if SedTemplate == 'flat':
            for f in filters:
                self.mags[f] = rmag
        else:
            self.mags = mafUtils.stellarMags(SedTemplate, rmag=rmag)

    def run(self, dataSlice, slicePoint=None):

        if np.size(dataSlice) < 2:
            return self.badval
        filters = np.unique(dataSlice[self.filterCol])
        snr = np.zeros(len(dataSlice), dtype='float')
        # compute SNR for all observations
        for filt in filters:
            good = np.where(dataSlice[self.filterCol] == filt)
            snr[good] = mafUtils.m52snr(self.mags[filt], dataSlice[self.m5Col][good])
        # Compute total parallax distance
        pf = np.sqrt(dataSlice['ra_pi_amp']**2+dataSlice['dec_pi_amp']**2)
        # Correlation between parallax factor and hour angle
        aboveLimit = np.where(snr >= self.snrLimit)[0]
        if np.size(aboveLimit) < 2:
            return self.badval
        rho, p = spearmanr(pf[aboveLimit], dataSlice[self.haCol][aboveLimit])
        return rho

# Check radius of observations to look for calibration effects.


def calcDist_cosines(RA1, Dec1, RA2, Dec2):
    # taken from simSelfCalib.py
    """Calculates distance on a sphere using spherical law of cosines.

    Give this function RA/Dec values in radians. Returns angular distance(s), in radians.
    Note that since this is all numpy, you could input arrays of RA/Decs."""
    # This formula can have rounding errors for case where distances are small.
    # Oh, the joys of wikipedia - http://en.wikipedia.org/wiki/Great-circle_distance
    # For the purposes of these calculations, this is probably accurate enough.
    D = np.sin(Dec2)*np.sin(Dec1) + np.cos(Dec1)*np.cos(Dec2)*np.cos(RA2-RA1)
    D = np.arccos(D)
    return D


class RadiusObsMetric(BaseMetric):
    """find the radius in the focal plane. """

    def __init__(self, metricName='radiusObs', raCol='fieldRA', decCol='fieldDec',
                 units='radians', **kwargs):
        self.raCol = raCol
        self.decCol = decCol
        super(RadiusObsMetric, self).__init__(col=[self.raCol, self.decCol],
                                              metricName=metricName, units=units, **kwargs)

    def run(self, dataSlice, slicePoint):
        ra = slicePoint['ra']
        dec = slicePoint['dec']
        distances = calcDist_cosines(ra, dec, dataSlice[self.raCol], dataSlice[self.decCol])
        return distances

    def reduceMean(self, distances):
        return np.mean(distances)

    def reduceRMS(self, distances):
        return np.std(distances)

    def reduceFullRange(self, distances):
        return np.max(distances)-np.min(distances)
