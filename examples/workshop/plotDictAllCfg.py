# Examples of all the plotting dictionary options

from lsst.sims.maf.driver.mafConfig import configureSlicer, configureMetric, makeDict

root.outputDir = './PlotDict'
root.dbAddress = {'dbAddress': 'sqlite:///opsimblitz2_1060_sqlite.db'}
root.opsimName = 'ob2_1060'
nside = 16
slicerList = []


plotDict = {'title': 'title!', 'cmap': 'RdBu', 'xlabel': 'xlabel!', 'ylabel': 'ylabel!',
            'label': 'label!', 'addLegend': True, 'color': 'r', 'bins': 150,
            'cbarFormat': '%.4g', 'cumulative': True, 'logScale': True, 'colorMin': 0.65, 'colorMax': 1.5,
            'xMin': 0.5, 'xMax': 1.6, 'linestyle': '--', 'maxl': 40, 'removeDipole': False}


m1 = configureMetric('MeanMetric', plotDict=plotDict, kwargs={'col': 'finSeeing', 'metricName': 'wplotdict'})
m2 = configureMetric('MeanMetric', kwargs={'col': 'finSeeing'})

metricDict = makeDict(m1, m2)

slicer = configureSlicer('HealpixSlicer', kwargs={"nside": nside},
                         metricDict = metricDict, constraints=['filter="r"'])
# For skymap units, title, ylog, cbarFormat, cmap, percentileClip, plotMin, plotMax, zp, normVal
# also on hist:  ylabel, bins, cumulative,ylog, color, scale, label, addLegend

slicerList.append(slicer)

plotDict = {'title': 'title!', 'xMin': 0.5, 'xMax': 1.7, 'ylabel': 'ylabel!',
            'xlabel': 'xlabel!', 'label': 'label!', 'addLegend': True, 'color': 'r',
            'yMin': 0.1, 'yMax': 10000., 'logScale': True, 'linestyle': '--'}


m1 = configureMetric('CountMetric', kwargs={'col': 'finSeeing', 'metricName': 'wplotdict'}, plotDict=plotDict)
m2 = configureMetric('CountMetric', kwargs={'col': 'finSeeing'})

metricDict = makeDict(m1, m2)
slicer = configureSlicer('OneDSlicer', kwargs={'sliceColName': 'finSeeing'},
                         metricDict = metricDict, constraints=['filter="r"'])
slicerList.append(slicer)

# for OneD:  title, units, label, addLegend, legendloc, filled, alpha,
# ylog, ylabel, xlabel, yMin, yMax, xMin, xMax


root.slicers = makeDict(*slicerList)
