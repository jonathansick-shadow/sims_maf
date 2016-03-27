import os
import numpy as np
import warnings
import matplotlib.pyplot as plt
import lsst.sims.maf.utils as utils

__all__ = ['PlotHandler', 'BasePlotter']


class BasePlotter(object):
    """
    Serve as the base type for MAF plotters and example of API.
    """

    def __init__(self):
        self.plotType = None
        self.defaultPlotDict = None

    def __call__(self, metricValue, slicer, userPlotDict, fignum=None):
        pass


class PlotHandler(object):

    def __init__(self, outDir='.', resultsDb=None, savefig=True,
                 figformat='pdf', dpi=600, thumbnail=True):
        self.outDir = outDir
        self.resultsDb = resultsDb
        self.savefig = savefig
        self.figformat = figformat
        self.dpi = dpi
        self.thumbnail = thumbnail
        self.filtercolors = {'u': 'cyan', 'g': 'g', 'r': 'y',
                             'i': 'r', 'z': 'm', 'y': 'k', ' ': None}
        self.filterorder = {' ': -1, 'u': 0, 'g': 1, 'r': 2, 'i': 3, 'z': 4, 'y': 5}

    def setMetricBundles(self, mBundles):
        """
        Set the metric bundle or bundles (list or dictionary).
        Reuse the PlotHandler by resetting this reference.
        The metric bundles have to have the same slicer.
        """
        self.mBundles = []
        self.plotDicts = []
        # Try to add the metricBundles in filter order.
        if isinstance(mBundles, dict):
            for mB in mBundles.itervalues():
                vals = mB.fileRoot.split('_')
                forder = [self.filterorder.get(f, None) for f in vals if len(f) == 1]
                forder = [o for o in forder if o is not None]
                if len(forder) == 0:
                    forder = len(self.mBundles)
                else:
                    forder = forder[-1]
                self.mBundles.insert(forder, mB)
            self.slicer = self.mBundles[0].slicer
        else:
            for mB in mBundles:
                vals = mB.fileRoot.split('_')
                forder = [self.filterorder.get(f, None) for f in vals if len(f) == 1]
                forder = [o for o in forder if o is not None]
                if len(forder) == 0:
                    forder = len(self.mBundles)
                else:
                    forder = forder[-1]
                self.mBundles.insert(forder, mB)
            self.slicer = self.mBundles[0].slicer
        for mB in self.mBundles:
            if mB.slicer.slicerName != self.slicer.slicerName:
                raise ValueError('MetricBundle items must have the same type of slicer')
        self._combineMetricNames()
        self._combineRunNames()
        self._combineMetadata()
        self._combineSql()
        self.setPlotDicts(reset=True)

    def setPlotDicts(self, plotDicts=None, plotFunc=None, reset=False):
        """
        Set or update (or 'reset') the plotDict for the (possibly joint) plots.

        Resolution is:
        auto-generated items (colors/labels/titles)
        < anything previously set in the plotHandler
        < defaults set by the plotter
        < explicitly set items in the metricBundle plotDict
        < explicitly set items in the plotDicts list passed to this method.
        """
        if reset:
            # Have to explicitly set each dictionary to a (separate) blank dictionary.
            self.plotDicts = [{} for b in self.mBundles]

        if isinstance(plotDicts, dict):
            # We were passed a single dictionary, not a list.
            singleDict = plotDicts
            # This is okay because we won't update plotDicts.
            plotDicts = [singleDict] * len(self.mBundles)

        autoLabelList = self._buildLegendLabels()
        autoColorList = self._buildColors()
        autoCbar = self._buildCbarFormat()
        autoTitle = self._buildTitle()
        if plotFunc is not None:
            autoXlabel, autoYlabel = self._buildXYlabels(plotFunc)

        # Loop through each bundle and generate a plotDict for it.
        for i, bundle in enumerate(self.mBundles):
            tmpPlotDict = {}
            tmpPlotDict['title'] = autoTitle
            tmpPlotDict['label'] = autoLabelList[i]
            tmpPlotDict['color'] = autoColorList[i]
            tmpPlotDict['legendloc'] = 'upper right'
            tmpPlotDict['cbarFormat'] = autoCbar
            # Use anything previously set in the plotHandler, if it's not None.
            tmpPlotDict.update(self.plotDicts[i])
            # Reset plotDict items set explicitly by plotter.
            if plotFunc is not None:
                tmpPlotDict['xlabel'] = autoXlabel
                tmpPlotDict['ylabel'] = autoYlabel
                # Replace auto-generated plot dict items with things
                #  set by the plotterDefaults, if they are not None.
                plotterDefaults = plotFunc.defaultPlotDict
                for k, v in plotterDefaults.iteritems():
                    if v is not None:
                        tmpPlotDict[k] = v
            # Add/override the bundle plotDict parameters if they are set.
            tmpPlotDict.update(bundle.plotDict)
            # Finally, replace anything set explicitly by the user right now.
            if plotDicts is not None:
                tmpPlotDict.update(plotDicts[i])
            # And save this new dictionary back in the class.
            self.plotDicts[i] = tmpPlotDict

        # Check that the plotDicts do not conflict.
        self._checkPlotDicts()

    def _combineMetricNames(self):
        """
        Combine metric names.
        """
        # Find the unique metric names.
        self.metricNames = set()
        for mB in self.mBundles:
            self.metricNames.add(mB.metric.name)
        # Find a pleasing combination of the metric names.
        order = ['u', 'g', 'r', 'i', 'z', 'y']
        if len(self.metricNames) == 1:
            jointName = ' '.join(self.metricNames)
        else:
            # Split each unique name into a list to see if we can merge the names.
            nameLengths = [len(x.split()) for x in self.metricNames]
            nameLists = [x.split() for x in self.metricNames]
            # If the metric names are all the same length, see if we can combine any parts.
            if len(set(nameLengths)) == 1:
                jointName = []
                for i in range(nameLengths[0]):
                    tmp = set([x[i] for x in nameLists])
                    # Try to catch special case of filters and put them in order.
                    if tmp.intersection(order) == tmp:
                        filterlist = ''
                        for f in order:
                            if f in tmp:
                                filterlist += f
                        jointName.append(filterlist)
                    else:
                        # Otherwise, just join and put into jointName.
                        jointName.append(''.join(tmp))
                jointName = ' '.join(jointName)
            # If the metric names are not the same length, just join everything.
            else:
                jointName = ' '.join(self.metricNames)
        self.jointMetricNames = jointName

    def _combineRunNames(self):
        """
        Combine runNames.
        """
        self.runNames = set()
        for mB in self.mBundles:
            self.runNames.add(mB.runName)
        self.jointRunNames = ' '.join(self.runNames)

    def _combineMetadata(self):
        """
        Combine metadata.
        """
        metadata = set()
        for mB in self.mBundles:
            metadata.add(mB.metadata)
        self.metadata = metadata
        # Find a pleasing combination of the metadata.
        if len(metadata) == 1:
            self.jointMetadata = ' '.join(metadata)
        else:
            order = ['u', 'g', 'r', 'i', 'z', 'y']
            # See if there are any subcomponents we can combine,
            # splitting on some values we expect to separate metadata clauses.
            splitmetas = []
            for m in self.metadata:
                # Try to split metadata into separate phrases (filter / proposal / constraint..).
                if ' and ' in m:
                    m = m.split(' and ')
                elif ', ' in m:
                    m = m.split(', ')
                else:
                    m = [m, ]
                # Strip white spaces from individual elements.
                m = set([im.strip() for im in m])
                splitmetas.append(m)
            # Look for common elements and separate from the general metadata.
            common = set.intersection(*splitmetas)
            diff = [x.difference(common) for x in splitmetas]
            # Now look within the 'diff' elements and see if there are any common words to split off.
            diffsplit = []
            for d in diff:
                if len(d) > 0:
                    m = set([x.split() for x in d][0])
                else:
                    m = set()
                diffsplit.append(m)
            diffcommon = set.intersection(*diffsplit)
            diffdiff = [x.difference(diffcommon) for x in diffsplit]
            # If the length of any of the 'differences' is 0, then we should stop and not try to subdivide.
            lengths = [len(x) for x in diffdiff]
            if min(lengths) == 0:
                # Sort them in order of length (so it goes 'g', 'g dithered', etc.)
                tmp = []
                for d in diff:
                    tmp.append(list(d)[0])
                diff = tmp
                xlengths = [len(x) for x in diff]
                idx = np.argsort(xlengths)
                diffdiff = [diff[i] for i in idx]
                diffcommon = []
            else:
                # diffdiff is the part where we might expect our filter values to appear;
                # try to put this in order.
                diffdiffOrdered = []
                diffdiffEnd = []
                for f in order:
                    for d in diffdiff:
                        if len(d) == 1:
                            if list(d)[0] == f:
                                diffdiffOrdered.append(d)
                for d in diffdiff:
                    if d not in diffdiffOrdered:
                        diffdiffEnd.append(d)
                diffdiff = diffdiffOrdered + diffdiffEnd
                diffdiff = [' '.join(c) for c in diffdiff]
            # And put it all back together.
            combo = (', '.join([''.join(c) for c in diffdiff]) + ' ' +
                     ' '.join([''.join(d) for d in diffcommon]) + ' ' +
                     ' '.join([''.join(e) for e in common]))
            self.jointMetadata = combo

    def _combineSql(self):
        """
        Combine the sql constraints.
        """
        sqlconstraints = set()
        for mB in self.mBundles:
            sqlconstraints.add(mB.sqlconstraint)
        self.sqlconstraints = '; '.join(sqlconstraints)

    def _buildTitle(self):
        """
        Build a plot title from the metric names, runNames and metadata.
        """
        # Create a plot title from the unique parts of the metric/runName/metadata.
        plotTitle = ''
        if len(self.runNames) == 1:
            plotTitle += list(self.runNames)[0]
        if len(self.metadata) == 1:
            plotTitle += ' ' + list(self.metadata)[0]
        if len(self.metricNames) == 1:
            plotTitle += ': ' + list(self.metricNames)[0]
        if plotTitle == '':
            # If there were more than one of everything above, use joint metadata and metricNames.
            plotTitle = self.jointMetadata + ' ' + self.jointMetricNames
        return plotTitle

    def _buildXYlabels(self, plotFunc):
        """
        Build a plot x and y label.
        """
        if plotFunc.plotType == 'BinnedData':
            if len(self.mBundles) == 1:
                mB = self.mBundles[0]
                xlabel = mB.slicer.sliceColName + ' (' + mB.slicer.sliceColUnits + ')'
                ylabel = mB.metric.name + ' (' + mB.metric.units + ')'
            else:
                xlabel = set()
                for mB in self.mBundles:
                    xlabel.add(mB.slicer.sliceColName)
                xlabel = ', '.join(xlabel)
                ylabel = self.jointMetricNames
        else:
            if len(self.mBundles) == 1:
                mB = self.mBundles[0]
                xlabel = mB.metric.name
                if mB.metric.units is not None:
                    if len(mB.metric.units) > 0:
                        xlabel += ' (' + mB.metric.units + ')'
                ylabel = None
            else:
                xlabel = self.jointMetricNames
                ylabel = set()
                for mB in self.mBundles:
                    if 'ylabel' in mB.plotDict:
                        ylabel.add(mB.plotDict['ylabel'])
                if len(ylabel) == 1:
                    ylabel = list(ylabel)[0]
                else:
                    ylabel = None
        return xlabel, ylabel

    def _buildLegendLabels(self):
        """
        Build a set of legend labels, using parts of the runName/metadata/metricNames that change.
        """
        if len(self.mBundles) == 1:
            return [None]
        labels = []
        for mB in self.mBundles:
            if 'label' in mB.plotDict:
                label = mB.plotDict['label']
            else:
                label = ''
                if len(self.runNames) > 1:
                    label += mB.runName
                if len(self.metadata) > 1:
                    label += ' ' + mB.metadata
                if len(self.metricNames) > 1:
                    label += ' ' + mB.metric.name
            labels.append(label)
        return labels

    def _buildColors(self):
        """
        Try to set an appropriate range of colors for the metric Bundles.
        """
        if len(self.mBundles) == 1:
            if 'color' in self.mBundles[0].plotDict:
                return [self.mBundles[0].plotDict['color']]
            else:
                return ['b']
        colors = []
        for mB in self.mBundles:
            if 'color' in mB.plotDict:
                color = mB.plotDict['color']
            else:
                # If the filter is part of the sql constraint, we'll
                #  try to use that first.
                if 'filter' in mB.sqlconstraint:
                    vals = mB.sqlconstraint.split('"')
                    for v in vals:
                        if len(v) == 1:
                            # Guess that this is the filter value
                            color = self.filtercolors[v]
                else:
                    color = 'b'
            colors.append(color)
        # If we happened to end up with the same color throughout
        #  (say, the metrics were all in the same filter)
        #  then go ahead and generate random colors.
        if (len(self.mBundles) > 1) and (len(np.unique(colors)) == 1):
            colors = [np.random.rand(3,) for mB in self.mBundles]
        return colors

    def _buildCbarFormat(self):
        """
        Set the color bar format.
        """
        cbarFormat = None
        if len(self.mBundles) == 1:
            if self.mBundles[0].metric.metricDtype == 'int':
                cbarFormat = '%d'
        else:
            metricDtypes = set()
            for mB in self.mBundles:
                metricDtypes.add(mB.metric.metricDtype)
            if len(metricDtypes) == 1:
                if list(metricDtypes)[0] == 'int':
                    cbarFormat = '%d'
        return cbarFormat

    def _buildFileRoot(self, outfileSuffix=None):
        """
        Build a root filename for plot outputs.
        If there is only one metricBundle, this is equal to the metricBundle fileRoot + outfileSuffix.
        For multiple metricBundles, this is created from the runNames, metadata and metric names.

        If you do not wish to use the automatic filenames, then you could set 'savefig' to False and
          save the file manually to disk, using the plot figure numbers returned by 'plot'.
        """
        if len(self.mBundles) == 1:
            outfile = self.mBundles[0].fileRoot
        else:
            outfile = '_'.join([self.jointRunNames, self.jointMetricNames, self.jointMetadata])
            outfile += '_' + self.mBundles[0].slicer.slicerName[:4].upper()
        if outfileSuffix is not None:
            outfile += '_' + outfileSuffix
        outfile = utils.nameSanitize(outfile)
        return outfile

    def _buildDisplayDict(self):
        """
        Generate a display dictionary.
        This is most useful for when there are many metricBundles being combined into a single plot.
        """
        if len(self.mBundles) == 1:
            return self.mBundles[0].displayDict
        else:
            displayDict = {}
            group = set()
            subgroup = set()
            order = 0
            for mB in self.mBundles:
                group.add(mB.displayDict['group'])
                subgroup.add(mB.displayDict['subgroup'])
                if order < mB.displayDict['order']:
                    order = mB.displayDict['order'] + 1
            displayDict['order'] = order
            if len(group) > 1:
                displayDict['group'] = 'Comparisons'
            else:
                displayDict['group'] = list(group)[0]
            if len(subgroup) > 1:
                displayDict['subgroup'] = 'Comparisons'
            else:
                displayDict['subgroup'] = list(subgroup)[0]

            displayDict['caption'] = ('%s metric(s) calculated on a %s grid, for opsim runs %s, for metadata values of %s.' % (
                self.jointMetricNames, self.mBundles[0].slicer.slicerName, self.jointRunNames, self.jointMetadata))

            return displayDict

    def _checkPlotDicts(self):
        """
        Check to make sure there are no conflicts in the plotDicts that are being used
        """

        # Check that the length is OK
        if len(self.plotDicts) != len(self.mBundles):
            raise ValueError('plotDicts (%i) must be same length as mBundles (%i)'
                             % (len(self.plotDicts), len(self.mBundles)))

        # These are the keys that need to match (or be None)
        keys2Check = ['xlim', 'ylim', 'legendloc', 'colorMin', 'colorMax', 'title']

        reset_keys = []
        for key in keys2Check:
            values = [pd[key] for pd in self.plotDicts if key in pd]
            if len(np.unique(values)) > 1:
                warnings.warn('Found more than one value to be set for "%s" in the plotDicts.' % (key) +
                              ' Will reset to default value')
                reset_keys.append(key)

        # Most of the defaults can be set to None safely.
        for key in reset_keys:
            for pd in self.plotDicts:
                pd[key] = None

        # But for some, we can/should do better.
        if 'title' in reset_keys:
            title = self._buildTitle()
            for pd in self.plotDicts:
                pd['title'] = title

    def plot(self, plotFunc, plotDicts=None, outfileSuffix=None):
        """
        Create plot for mBundles, using plotFunc.

        plotDicts:  List of plotDicts if one wants to use a _new_ plotDict per MetricBundle.
        """

        if not plotFunc.objectPlotter:
            # Check that metricValues type and plotter are compatible (most are float/float, but
            #  some plotters expect object data .. and some only do sometimes).
            for mB in self.mBundles:
                if mB.metric.metricDtype == 'object':
                    metricIsColor = mB.plotDict.get('metricIsColor', False)
                    if not metricIsColor:
                        warnings.warn('Cannot plot object metric values with this plotter.')
                        return

        # Update x/y labels using plotType.
        self.setPlotDicts(plotDicts=None, plotFunc=plotFunc, reset=False)
        # Then add any plotDicts passed here, but only as temporary set of plotDicts (userPlotDicts).
        if isinstance(plotDicts, dict):
            # We were passed a single dictionary instead of a list.
            singleDict = plotDicts
            plotDicts = [singleDict] * len(self.mBundles)
        userPlotDicts = [{} for b in self.mBundles]
        for i in range(len(self.mBundles)):
            userPlotDicts[i].update(self.plotDicts[i])
            if plotDicts is not None:
                userPlotDicts[i].update(plotDicts[i])

        # Set outfile name.
        outfile = self._buildFileRoot(outfileSuffix)
        plotType = plotFunc.plotType
        # Make plot.
        fignum = None
        for mB, plotDict in zip(self.mBundles, userPlotDicts):
            if mB.metricValues is None:
                # Skip this metricBundle.
                warnings.warn('MetricBundle (fileRoot=%s) has no attribute metricValues' % (mB.fileRoot) +
                              ' Either it has not been calculated or it has been deleted.')
            else:
                fignum = plotFunc(mB.metricValues, mB.slicer, plotDict, fignum=fignum)
        if len(self.mBundles) > 1:
            # Add a legend if more than metricValue being plotted.
            plotType = 'Combo' + plotType
            plt.figure(fignum)
            plt.legend(loc=userPlotDicts[0]['legendloc'], fancybox=True, fontsize='smaller')
        # Save to disk and file info to resultsDb if desired.
        if self.savefig:
            fig = plt.figure(fignum)
            plotFile = outfile + '_' + plotType + '.' + self.figformat
            fig.savefig(os.path.join(self.outDir, plotFile), figformat=self.figformat, dpi=self.dpi)
            if self.thumbnail:
                thumbFile = 'thumb.' + outfile + '_' + plotType + '.png'
                plt.savefig(os.path.join(self.outDir, thumbFile), dpi=72)
            # Save information about the file to the resultsDb.
            if self.resultsDb:
                metricId = self.resultsDb.updateMetric(self.jointMetricNames, self.slicer.slicerName,
                                                       self.jointRunNames, self.sqlconstraints,
                                                       self.jointMetadata, None)
                # Add information to displays table (without overwriting previous information, if present).
                displayDict = self._buildDisplayDict()
                self.resultsDb.updateDisplay(metricId=metricId, displayDict=displayDict, overwrite=False)
                # Add plot information to plot table.
                self.resultsDb.updatePlot(metricId=metricId, plotType=plotType, plotFile=plotFile)
        return fignum
