const NodeMediaServer = require('node-media-server');

const config = {
  rtmp: { port: 1936, chunk_size: 1024, gop_cache: false, ping: 10, ping_timeout: 30 },
  http: { port: 8000, allow_origin: '*' }
};

const nms = new NodeMediaServer(config);
nms.run();

console.log('==================================================');
console.log('  RTMP Server running on port 1936');
console.log('==================================================');
console.log('  In DJI Mimo enter:');
console.log('  rtmp://10.243.253.63:1936/live/stream');
console.log('  Waiting for stream...');

nms.on('prePublish', (id, StreamPath) => {
    console.log('Stream connected: ' + StreamPath);
    console.log('Now run: python test_dji_wireless.py');
});
