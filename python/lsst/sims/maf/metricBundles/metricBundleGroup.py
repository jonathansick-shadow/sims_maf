import os
import numpy as np
import numpy.ma as ma
import matplotlib.pyplot as plt
from collections import OrderedDict

import lsst.sims.maf.db as db
import lsst.sims.maf.utils as utils
from lsst.sims.maf.plots import PlotHandler
import lsst.sims.maf.maps as maps
from .metricBundle import MetricBundle, createEmptyMetricBundle
import warnings

__all__ = ['makeBundlesDictFromList', 'MetricBundleGroup']


def makeBundlesDictFromList(bundleList):
    """Utility to convert a list of MetricBundles into a dictionary, keyed by the fileRoot names.

    Raises an exception if the fileroot duplicates another metricBundle.
    (Note this should alert to potential cases of filename duplication).

    Parameters
    ----------
    bundleList : List[MetricBundle]
    """
    bDict = {}
    for b in bundleList:
        if b.fileRoot in bDict:
            raise NameError('More than one metricBundle is using the same fileroot, %s' % (b.fileRoot))
        bDict[b.fileRoot] = b
    return bDict


class MetricBundleGroup(object):
    """The MetricBundleGroup exists to calculate the metric values for a group of
    MetricBundles.

    The MetricBundleGroup will query data from a single database table (for multiple
    sqlconstraints), use that data to calculate metric values for multiple slicers,
    and calculate summary statistics and generate plots for all metrics included in
    the dictionary passed to the MetricBundleGroup.

    We calculate the metric values here, rather than in the individual MetricBundles,
    because it is much more efficient to step through a slicer once (and calculate all
    the relevant metric values at each point) than it is to repeat this process multiple times.

    The MetricBundleGroup also determines how to efficiently group the MetricBundles
    to reduce the number of sql queries of the database, grabbing larger chunks of data at once.

    Parameters
    ----------
    bundleDict : dict[MetricBundle]
        Individual MetricBundles should be placed into a dictionary, and then passed to
        the MetricBundleGroup. The dictionary keys can then be used to identify MetricBundles
        if needed -- and to identify new MetricBundles which could be created if 'reduce'
        functions are run on a particular MetricBundle.
        A bundleDict can be conveniently created from a list of MetricBundles using
        makeBundlesDictFromList
    dbObj : Database
        The database object (typically an :class:`OpsimDatabase`) connected to the data to be used to
        calculate metrics.
        Advanced use: It is possible to set this to None, in which case data should be passed
        directly to the runCurrent method (and runAll should not be used).
    outDir : Optional[str]
        Directory to save the metric results. Default is the current directory.
    resultsDb : Optional[ResultsDb]
        A results database. If not specified, one will be created in the outDir.
        This database saves information about the metrics calculated, including their summary statistics.
    verbose : Optional[bool]
        Flag to turn on/off verbose feedback.
    saveEarly : Optional[bool]
        If True, metric values will be saved immediately after they are first calculated (to prevent
        data loss) as well as after summary statistics are calculated.
        If False, metric values will only be saved after summary statistics are calculated.
    dbTable : Optional[str]
        The name of the table in the dbObj to query for data.
    """
    def __init__(self, bundleDict, dbObj, outDir='.', resultsDb=None, verbose=True,
                 saveEarly=True, dbTable='Summary'):
        """Set up the MetricBundleGroup.
        """
        # Print occasional messages to screen.
        self.verbose = verbose
        # Save metric results as soon as possible (in case of crash).
        self.saveEarly = saveEarly
        # Check for output directory, create it if needed.
        self.outDir = outDir
        if not os.path.isdir(self.outDir):
            os.makedirs(self.outDir)
        # Set the table we're going to be querying.
        self.dbTable = dbTable
        # Do some type checking on the MetricBundle dictionary.
        if not isinstance(bundleDict, dict):
            raise ValueError('bundleDict should be a dictionary containing MetricBundle objects.')
        for b in bundleDict.itervalues():
            if not isinstance(b, MetricBundle):
                raise ValueError('bundleDict should contain only MetricBundle objects.')
        # Identify the series of sqlconstraints.
        self.sqlconstraints = list(set([b.sqlconstraint for b in bundleDict.values()]))
        # Set the bundleDict (all bundles, with all sqlconstraints)
        self.bundleDict = bundleDict
        # Check the dbObj.
        if not isinstance(dbObj, db.Database):
            warnings.warn('Warning: dbObj should be an instantiated Database (or child) object.')
        self.dbObj = dbObj
        # Check the resultsDb (optional).
        if resultsDb is not None:
            if not isinstance(resultsDb, db.ResultsDb):
                raise ValueError('resultsDb should be an ResultsDb object')
        self.resultsDb = resultsDb

        # Dict to keep track of what's been run:
        self.hasRun = {}
        for bk in bundleDict:
            self.hasRun[bk] = False

    def _getDictSubset(self, origdict, subsetkeys):
        """Private utility to return a dictionary with a subset of an original dictionary,
        identified by subsetkeys.
        """
        newdict = {key: origdict.get(key) for key in subsetkeys}
        return newdict

    def setCurrent(self, sqlconstraint):
        """Utility to set the currentBundleDict (i.e. a set of metricBundles with the same SQL constraint).

        Parameters
        ----------
        sqlconstraint : str
            The subset of MetricBundles with metricBundle.sqlconstraint == sqlconstraint will be
            included in a subset identified as the currentBundleDict.
            These are the active metrics to be calculated and plotted, etc.
        """
        self.currentBundleDict = {}
        for k, b in self.bundleDict.iteritems():
            if b.sqlconstraint == sqlconstraint:
                self.currentBundleDict[k] = b

    def _checkCompatible(self, metricBundle1, metricBundle2):
        """Check if two MetricBundles are "compatible".
        Compatible indicates that the sql constraints, the slicers, and the maps are the same, and
        that the stackers do not interfere with each other
        (i.e. are not trying to set the same column in different ways).
        Returns True if the MetricBundles are compatible, False if not.

        Parameters
        ----------
        metricBundle1 : MetricBundle
        metricBundle2 : MetricBundle

        Returns
        -------
        bool
        """
        if metricBundle1.sqlconstraint != metricBundle2.sqlconstraint:
            return False
        if metricBundle1.slicer != metricBundle2.slicer:
            return False
        if metricBundle1.mapsList.sort() != metricBundle2.mapsList.sort():
            return False
        for stacker in metricBundle1.stackerList:
            for stacker2 in metricBundle2.stackerList:
                # If the stackers have different names, that's OK, and if they are identical, that's ok.
                if (stacker.__class__.__name__ == stacker2.__class__.__name__) & (stacker != stacker2):
                    return False
        # But if we got this far, everything matches.
        return True

    def _findCompatibleLists(self):
        """Find sets of compatible metricBundles from the currentBundleDict.
        """
        # CompatibleLists stores a list of lists;
        #   each (nested) list contains the bundleDict _keys_ of a compatible set of metricBundles.
        #
        compatibleLists = []
        for k, b in self.currentBundleDict.iteritems():
            foundCompatible = False
            for compatibleList in compatibleLists:
                comparisonMetricBundleKey = compatibleList[0]
                compatible = self._checkCompatible(self.bundleDict[comparisonMetricBundleKey], b)
                if compatible:
                    # Must compare all metricBundles in each subset (if they are a potential match),
                    #  as the stackers could be different (and one could be incompatible,
                    #  not necessarily the first)
                    for comparisonMetricBundleKey in compatibleList[1:]:
                        compatible = self._checkCompatible(self.bundleDict[comparisonMetricBundleKey], b)
                        if not compatible:
                            # If we find one which is not compatible, stop and go on to the
                            # next subset list.
                            break
                    # Otherwise, we reached the end of the subset and they were all compatible.
                    foundCompatible = True
                    compatibleList.append(k)
            if not foundCompatible:
                # Didn't find a pre-existing compatible set; make a new one.
                compatibleLists.append([k, ])
        self.compatibleLists = compatibleLists

    def runAll(self, clearMemory=False, plotNow=False, plotKwargs=None):
        """Runs all the metricBundles in the metricBundleGroup, over all sqlconstraints.

        Calculates metric values, then runs reduce functions and summary statistics for
        all MetricBundles.

        Parameters
        ----------
        clearMemory : Optional[bool]
            If True, deletes metric values from memory after running each sqlconstraint group.
        plotNow : Optional[bool]
            If True, plots the metric values immediately after calculation.
        plotKwargs : Optional[kwargs]
            kwargs to pass to plotCurrent.
        """
        for sqlconstraint in self.sqlconstraints:
            # Set the 'currentBundleDict' which is a dictionary of the metricBundles which match this
            #  sqlconstraint.
            self.setCurrent(sqlconstraint)
            self.runCurrent(sqlconstraint, clearMemory=clearMemory,
                            plotNow=plotNow, plotKwargs=plotKwargs)

    def runCurrent(self, sqlconstraint, simData=None, clearMemory=False, plotNow=False, plotKwargs=None):
        """Run all the metricBundles which match this sqlconstraint in the metricBundleGroup.

        Calculates the metric values, then runs reduce functions and summary statistics for
        metrics in the current set only (see self.setCurrent).

        Parameters
        ----------
        sqlconstraint : str
           Sqlconstraint to use to set the currently active metrics
        simData : Optional[numpy.ndarray]
           If simData is not None, then this numpy structured array is used instead of querying
           data from the dbObj.
        clearMemory : Optional[bool]
           If True, metric values are deleted from memory after they are calculated (and saved to disk).
        plotNow : Optional[bool]
           Plot immediately after calculating metric values (instead of the usual procedure, which
           is to plot after metric values are calculated for all sqlconstraints).
        plotKwargs : Optional[kwargs]
           Plotting kwargs to pass to plotCurrent.
        """
        # Build list of all the columns needed from the database.
        self.dbCols = []
        for b in self.currentBundleDict.itervalues():
            self.dbCols.extend(b.dbCols)
        self.dbCols = list(set(self.dbCols))

        # Can pass simData directly (if had other method for getting data)
        if simData is not None:
            self.simData = simData

        else:
            self.simData = None
            # Query for the data.
            try:
                self.getData(sqlconstraint)
            except UserWarning:
                warnings.warn('No data matching sqlconstraint %s' % sqlconstraint)
                return
            except ValueError:
                warnings.warn('One of the columns requested from the database was not available.' +
                              ' Skipping sqlconstraint %s' % sqlconstraint)
                return

        # Find compatible subsets of the MetricBundle dictionary,
        # which can be run/metrics calculated/ together.
        self._findCompatibleLists()

        for compatibleList in self.compatibleLists:
            if self.verbose:
                print 'Running: ', compatibleList
            self._runCompatible(compatibleList)
            if self.verbose:
                print 'Completed metric generation.'
            for key in compatibleList:
                self.hasRun[key] = True
        # Run the reduce methods.
        if self.verbose:
            print 'Running reduce methods.'
        self.reduceCurrent()
        # Run the summary statistics.
        if self.verbose:
            print 'Running summary statistics.'
        self.summaryCurrent()
        if self.verbose:
            print 'Completed.'
        if plotNow:
            if plotKwargs is None:
                self.plotCurrent()
            else:
                self.plotCurrent(**plotKwargs)
        # Optionally: clear results from memory.
        if clearMemory:
            for b in self.currentBundleDict.itervalues():
                b.metricValues = None
            if self.verbose:
                print 'Deleted metricValues from memory.'

    def getData(self, sqlconstraint):
        """Query the data from the database.

        The currently bundleDict should generally be set before calling getData (using setCurrent).

        Parameters
        ----------
        sqlconstraint : str
           The sqlconstraint for the currently active set of MetricBundles.
        """
        if self.verbose:
            if sqlconstraint == '':
                print "Querying database with no constraint."
            else:
                print "Querying database with constraint %s" % (sqlconstraint)
        # Note that we do NOT run the stackers at this point (this must be done in each 'compatible' group).
        if self.dbTable != 'Summary':
            distinctExpMJD = False
            groupBy = None
        else:
            distinctExpMJD = True
            groupBy = 'expMJD'
        self.simData = utils.getSimData(self.dbObj, sqlconstraint, self.dbCols,
                                        tableName=self.dbTable, distinctExpMJD=distinctExpMJD,
                                        groupBy=groupBy)

        if self.verbose:
            print "Found %i visits" % (self.simData.size)

        # Query for the fieldData if we need it for the opsimFieldSlicer.
        needFields = [b.slicer.needsFields for b in self.currentBundleDict.itervalues()]
        if True in needFields:
            self.fieldData = utils.getFieldData(self.dbObj, sqlconstraint)
        else:
            self.fieldData = None

    def _runCompatible(self, compatibleList):
        """Runs a set of 'compatible' metricbundles in the MetricBundleGroup dictionary,
        identified by 'compatibleList' keys.

        A compatible list of MetricBundles is a subset of the currentBundleDict.
        The currentBundleDict == set of MetricBundles with the same sqlconstraint.
        The compatibleBundles == set of MetricBundles with the same sqlconstraint, the same
        slicer, the same maps applied to the slicer, and stackers which do not clobber each other's data.

        This is where the work of calculating the metric values is done.
        """

        if len(self.simData) == 0:
            return

        # Grab a dictionary representation of this subset of the dictionary, for easier iteration.
        bDict = self._getDictSubset(self.currentBundleDict, compatibleList)

        compatMaps = []
        compatStackers = []
        for b in bDict.itervalues():
            compatMaps.extend(b.mapsList)
            for stacker in b.stackerList:
                if stacker not in compatStackers:
                    compatStackers.append(stacker)

        # Add maps. If a metric knows that it requires a map that isn't already
        # in any of the bundles, instatiate it.
        compatMaps = list(set(compatMaps))
        mapNames = [compatMap.__class__.__name__ for compatMap in compatMaps]
        for b in bDict.itervalues():
            if hasattr(b.metric, 'maps'):
                for mapName in b.metric.maps:
                    if mapName not in mapNames:
                        tempMap = getattr(maps, mapName)()
                        compatMaps.append(tempMap)
                        mapNames.append(mapName)

        # Run stackers.
        for stacker in compatStackers:
            # Note that stackers will clobber previously existing rows with the same name.
            self.simData = stacker.run(self.simData)

        # Pull out one of the slicers to use as our 'slicer'.
        # This will be forced back into all of the metricBundles at the end (so that they track
        #  the same metadata such as the slicePoints, in case the same actual object wasn't used).
        slicer = bDict.itervalues().next().slicer
        if (slicer.slicerName == 'OpsimFieldSlicer'):
            slicer.setupSlicer(self.simData, self.fieldData, maps=compatMaps)
        else:
            slicer.setupSlicer(self.simData, maps=compatMaps)
        # Copy the slicer (after setup) back into the individual metricBundles.
        if slicer.slicerName != 'HealpixSlicer' or slicer.slicerName != 'UniSlicer':
            for b in bDict.itervalues():
                b.slicer = slicer

        # Set up (masked) arrays to store metric data in each metricBundle.
        for b in bDict.itervalues():
            b._setupMetricValues()

        # Set up an ordered dictionary to be the cache if needed:
        # (Currently using OrderedDict, it might be faster to use 2 regular Dicts instead)
        if slicer.cacheSize > 0:
            cacheDict = OrderedDict()
            cache = True
        else:
            cache = False
        # Run through all slicepoints and calculate metrics.
        for i, slice_i in enumerate(slicer):
            slicedata = self.simData[slice_i['idxs']]
            if len(slicedata) == 0:
                # No data at this slicepoint. Mask data values.
                for b in bDict.itervalues():
                    b.metricValues.mask[i] = True
            else:
                # There is data! Should we use our data cache?
                if cache:
                    # Make the data idxs hashable.
                    cacheKey = frozenset(slice_i['idxs'])
                    # If key exists, set flag to use it, otherwise add it
                    if cacheKey in cacheDict:
                        useCache = True
                        cacheVal = cacheDict[cacheKey]
                        # Move this value to the end of the OrderedDict
                        del cacheDict[cacheKey]
                        cacheDict[cacheKey] = cacheVal
                    else:
                        cacheDict[cacheKey] = i
                        useCache = False
                    for b in bDict.itervalues():
                        if useCache:
                            b.metricValues.data[i] = b.metricValues.data[cacheDict[cacheKey]]
                        else:
                            b.metricValues.data[i] = b.metric.run(slicedata, slicePoint=slice_i['slicePoint'])
                    # If we are above the cache size, drop the oldest element from the cache dict.
                    if len(cacheDict) > slicer.cacheSize:
                        del cacheDict[cacheDict.keys()[0]]

                # Not using memoize, just calculate things normally
                else:
                    for b in bDict.itervalues():
                        b.metricValues.data[i] = b.metric.run(slicedata, slicePoint=slice_i['slicePoint'])
        # Mask data where metrics could not be computed (according to metric bad value).
        for b in bDict.itervalues():
            if b.metricValues.dtype.name == 'object':
                for ind, val in enumerate(b.metricValues.data):
                    if val is b.metric.badval:
                        b.metricValues.mask[ind] = True
            else:
                # For some reason, this doesn't work for dtype=object arrays.
                b.metricValues.mask = np.where(b.metricValues.data == b.metric.badval,
                                               True, b.metricValues.mask)

        # Save data to disk as we go, although this won't keep summary values, etc. (just failsafe).
        if self.saveEarly:
            for b in bDict.itervalues():
                b.write(outDir=self.outDir, resultsDb=self.resultsDb)

    def reduceAll(self, updateSummaries=True):
        """Run the reduce methods for all metrics in bundleDict.

        Running this method, for all MetricBundles at once, assumes that clearMemory was False.

        Parameters
        ----------
        updateSummaries : Optional[bool]
            If True, summary metrics are removed from the top-level (non-reduced)
            MetricBundle. Usually this should be True, as summary metrics are generally
            intended to run on the simpler data produced by reduce metrics.
        """
        for sqlconstraint in self.sqlconstraints:
            self.setCurrent(sqlconstraint)
            self.reduceCurrent(updateSummaries=updateSummaries)

    def reduceCurrent(self, updateSummaries=True):
        """Run all reduce functions for the metricbundle in the currently active set of MetricBundles.

        Parameters
        ----------
        updateSummaries : Optional[bool]
            If True, summary metrics are removed from the top-level (non-reduced)
            MetricBundle. Usually this should be True, as summary metrics are generally
            intended to run on the simpler data produced by reduce metrics.
        """
        # Create a temporary dictionary to hold the reduced metricbundles.
        reduceBundleDict = {}
        for b in self.currentBundleDict.itervalues():
            # If there are no reduce functions associated with the metric, skip this metricBundle.
            if len(b.metric.reduceFuncs) > 0:
                # Apply reduce functions, creating a new metricBundle in the process (new metric values).
                for reduceFunc in b.metric.reduceFuncs.itervalues():
                    newmetricbundle = b.reduceMetric(reduceFunc)
                    # Add the new metricBundle to our metricBundleGroup dictionary.
                    name = newmetricbundle.metric.name
                    if name in self.bundleDict:
                        name = newmetricbundle.fileRoot
                    reduceBundleDict[name] = newmetricbundle
                    if self.saveEarly:
                        newmetricbundle.write(outDir=self.outDir, resultsDb=self.resultsDb)
                # Remove summaryMetrics from top level metricbundle if desired.
                if updateSummaries:
                    b.summaryMetrics = []
        # Add the new metricBundles to the MetricBundleGroup dictionary.
        self.bundleDict.update(reduceBundleDict)
        # And add to to the currentBundleDict too, so we run as part of 'summaryCurrent'.
        self.currentBundleDict.update(reduceBundleDict)

    def summaryAll(self):
        """Run the summary statistics for all metrics in bundleDict.

        Calculating all summary statistics, for all MetricBundles, at this
        point assumes that clearMemory was False.
        """
        for sqlconstraint in self.sqlconstraints:
            self.setCurrent(sqlconstraint)
            self.summaryCurrent()

    def summaryCurrent(self):
        """Run summary statistics on all the metricBundles in the currently active set of MetricBundles.
        """
        for b in self.currentBundleDict.itervalues():
            b.computeSummaryStats(self.resultsDb)

    def plotAll(self, savefig=True, outfileSuffix=None, figformat='pdf', dpi=600, thumbnail=True,
                closefigs=True):
        """Generate all the plots for all the metricBundles in bundleDict.

        Generating all ploots, for all MetricBundles, at this point, assumes that
        clearMemory was False.

        Parameters
        ----------
        savefig : Optional[bool]
            If True, save figures to disk, to self.outDir directory.
        outfileSuffix : Optional[str]
            Append outfileSuffix to the end of every plot file generated. Useful for generating
            sequential series of images for movies.
        figformat : Optional[str]
            Matplotlib figure format to use to save to disk. Default pdf.
        dpi : Optional[str]
            DPI for matplotlib figure. Default 600.
        thumbnail : Optional[bool]
            If True, save a small thumbnail jpg version of the output file to disk as well.
            This is useful for showMaf web pages. Default True.
        closefigs : Optional[bool]
            Close the matplotlib figures after they are saved to disk. If many figures are
            generated, closing the figures saves significant memory. Default True.
        """
        for sqlconstraint in self.sqlconstraints:
            if self.verbose:
                print 'Plotting figures with %s sqlconstraint now.' % (sqlconstraint)
            self.setCurrent(sqlconstraint)
            self.plotCurrent(savefig=savefig, outfileSuffix=outfileSuffix, figformat=figformat, dpi=dpi,
                             thumbnail=thumbnail, closefigs=closefigs)

    def plotCurrent(self, savefig=True, outfileSuffix=None, figformat='pdf', dpi=600, thumbnail=True,
                    closefigs=True):
        """Generate the plots for the currently active set of MetricBundles.

        Parameters
        ----------
        savefig : Optional[bool]
            If True, save figures to disk, to self.outDir directory.
        outfileSuffix : Optional[str]
            Append outfileSuffix to the end of every plot file generated. Useful for generating
            sequential series of images for movies.
        figformat : Optional[str]
            Matplotlib figure format to use to save to disk. Default pdf.
        dpi : Optional[str]
            DPI for matplotlib figure. Default 600.
        thumbnail : Optional[bool]
            If True, save a small thumbnail jpg version of the output file to disk as well.
            This is useful for showMaf web pages. Default True.
        closefigs : Optional[bool]
            Close the matplotlib figures after they are saved to disk. If many figures are
            generated, closing the figures saves significant memory. Default True.
        """
        plotHandler = PlotHandler(outDir=self.outDir, resultsDb=self.resultsDb,
                                  savefig=savefig, figformat=figformat, dpi=dpi, thumbnail=thumbnail)
        for b in self.currentBundleDict.itervalues():
            b.plot(plotHandler=plotHandler, outfileSuffix=outfileSuffix, savefig=savefig)
            if closefigs:
                plt.close('all')
        if self.verbose:
            print 'Plotting complete.'

    def writeAll(self):
        """Save all the MetricBundles to disk.

        Saving all MetricBundles to disk at this point assumes that clearMemory was False.
        """
        for sqlconstraint in self.sqlconstraints:
            self.setCurrent(sqlconstraint)
            self.writeCurrent()

    def writeCurrent(self):
        """Save all the MetricBundles in the currently active set to disk.
        """
        if self.verbose:
            if self.saveEarly:
                print 'Re-saving metric bundles.'
            else:
                print 'Saving metric bundles.'
        for b in self.currentBundleDict.itervalues():
            b.write(outDir=self.outDir, resultsDb=self.resultsDb)

    def readAll(self):
        """Attempt to read all MetricBundles from disk.

        You must set the metrics/slicer/sqlconstraint/runName for a metricBundle appropriately;
        then this method will search for files in the location self.outDir/metricBundle.fileRoot.
        Reads all the files associated with all metricbundles in self.bundleDict.
        """
        reduceBundleDict = {}
        for b in self.bundleDict.itervalues():
            filename = os.path.join(self.outDir, b.fileRoot + '.npz')
            try:
                # Create a temporary metricBundle to read the data into.
                #  (we don't use b directly, as this overrides plotDict/etc).
                tmpBundle = createEmptyMetricBundle()
                tmpBundle.read(filename)
                # Copy the tmpBundle metricValues into b.
                b.metricValues = ma.copy(tmpBundle.metricValues)
                del tmpBundle
            except:
                warnings.warn('Warning: file %s not found, bundle not restored.' % filename)

                # Look to see if this is a complex metric, with associated 'reduce' functions,
                # and read those in too.
                if len(b.metric.reduceFuncs) > 0:
                    origMetricName = b.metric.name
                    for reduceFunc in b.metric.reduceFuncs.itervalues():
                        reduceName = origMetricName + '_' + reduceFunc.__name__.replace('reduce', '')
                        # Borrow the fileRoot in b (we'll reset it appropriately afterwards).
                        b.metric.name = reduceName
                        b._buildFileRoot()
                        filename = os.path.join(self.outDir, b.fileRoot + '.npz')
                        tmpBundle = createEmptyMetricBundle()
                        try:
                            tmpBundle.read(filename)
                            # This won't necessarily recreate the plotDict and displayDict exactly
                            # as they would have been made if you calculated the reduce metric from scratch.
                            # Perhaps update these metric reduce dictionaries after reading them in?
                            newmetricBundle = MetricBundle(metric=b.metric, slicer=b.slicer,
                                                           sqlconstraint=b.sqlconstraint,
                                                           stackerList=b.stackerList, runName=b.runName,
                                                           metadata=b.metadata,
                                                           plotDict=b.plotDict, displayDict=b.displayDict,
                                                           summaryMetrics=b.summaryMetrics,
                                                           mapsList=b.mapsList,
                                                           fileRoot=b.fileRoot, plotFuncs=b.plotFuncs)
                            newmetricBundle.metric.name = reduceName
                            newmetricBundle.metricValues = ma.copy(tmpBundle.metricValues)
                            del tmpBundle

                            # Add the new metricBundle to our metricBundleGroup dictionary.
                            name = newmetricBundle.metric.name
                            if name in self.bundleDict:
                                name = newmetricBundle.fileRoot
                            reduceBundleDict[name] = newmetricBundle
                        except:
                            warnings.warn('Warning: file %s not found, bundle not restored.' % filename)

                    # Remove summaryMetrics from top level metricbundle.
                    b.summaryMetrics = []
                    # Update parent MetricBundle name.
                    b.metric.name = origMetricName
                    b._buildFileRoot()
                if self.verbose:
                    print 'Read %s from disk.' % (b.fileRoot)
        # Add the reduce bundles into the bundleDict.
        self.bundleDict.update(reduceBundleDict)
