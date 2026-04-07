const monitoring = require('@google-cloud/monitoring');
const functions = require('@google-cloud/functions-framework');

const PROJECT_ID = 'sstr-492316';
const client = new monitoring.MetricServiceClient();

async function getApiUsage(serviceName) {
  const now = new Date();
  const startTime = new Date(now.getFullYear(), now.getMonth(), 1); // 月初

  const [timeSeries] = await client.listTimeSeries({
    name: `projects/${PROJECT_ID}`,
    filter: `metric.type="serviceruntime.googleapis.com/api/request_count" AND resource.labels.service="${serviceName}"`,
    interval: {
      startTime: { seconds: Math.floor(startTime.getTime() / 1000) },
      endTime: { seconds: Math.floor(now.getTime() / 1000) },
    },
    aggregation: {
      alignmentPeriod: { seconds: Math.floor((now - startTime) / 1000) },
      perSeriesAligner: 'ALIGN_SUM',
    },
  });

  let total = 0;
  for (const ts of timeSeries) {
    for (const point of ts.points) {
      total += Number(point.value.int64Value || point.value.doubleValue || 0);
    }
  }
  return total;
}

functions.http('sstrApi', async (req, res) => {
  // CORS
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'GET');
  if (req.method === 'OPTIONS') { res.status(204).send(''); return; }

  const path = req.path || '/';

  if (path === '/stats' || path === '/api/stats') {
    try {
      const [maps, dirs] = await Promise.all([
        getApiUsage('maps-backend.googleapis.com'),
        getApiUsage('routes.googleapis.com'),
      ]);
      // Also try legacy directions API name
      let dirs2 = 0;
      try {
        dirs2 = await getApiUsage('directions-backend.googleapis.com');
      } catch (e) {}

      res.json({
        maps,
        directions: dirs + dirs2,
        month: new Date().toISOString().slice(0, 7),
        timestamp: new Date().toISOString(),
      });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  } else {
    res.json({ status: 'ok', endpoints: ['/stats'] });
  }
});
