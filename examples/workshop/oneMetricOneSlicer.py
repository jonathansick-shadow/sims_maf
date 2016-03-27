# Here is an example of a very very simple MAF configuration driver script
# to run:
# runDriver.py oneMetricOneSlicer.py

# This script uses the LSST pex_config.  This is executed as a python script, but only things that
#  start with 'root.' are passed on to the driver script.

# Import MAF helper functions
from lsst.sims.maf.driver.mafConfig import configureSlicer, configureMetric, makeDict

# Set the output directory
root.outputDir = './OneMetric'
# Set the database to use (the example db included in the git repo)
root.dbAddress = {'dbAddress': 'sqlite:///opsimblitz2_1060_sqlite.db'}
# Name of this run (filename base)
root.opsimName = 'ob2_1060'

# Configure a metric to run. Compute the mean on the final delivered seeing.
# Once the mean seeing has been computed everywhere on the sky, compute the RMS as a summary statistic.
metric = configureMetric('MeanMetric', kwargs={'col': 'finSeeing'},
                         summaryStats={'RmsMetric': {}})

# Configure a slicer.  Use the Healpixslicer to compute the metric at points in the sky.
# Set the constraint as an empty string so all data is returned.
slicer = configureSlicer('HealpixSlicer', metricDict=makeDict(metric),
                         constraints=[''])

root.slicers = makeDict(slicer)

