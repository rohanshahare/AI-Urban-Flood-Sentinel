const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname, '..', '..');
const ffmpeg = 'C:\\Users\\91888\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.1-essentials_build\\bin\\ffmpeg.exe';
const source = path.join(__dirname, 'recordings', 'page@d736c533230fd36565d240c14d9998dd.webm');
const narration = path.join(__dirname, 'narration.wav');
const captions = path.join(__dirname, 'captions.srt');
const output = path.join(root, 'video_demo', 'AI_Urban_Flood_Sentinel_Demo.mp4');
const transition = 0.35;

// Each shot follows one synthesized narration paragraph; trim ranges are from the genuine browser capture.
const shots = [
  { from: 0, to: 10, focus: [960, 540], zoom: 1.0, label: 'Opening title' },
  { from: 10, to: 20, focus: [620, 105], zoom: 1.24, label: 'Dashboard KPIs' },
  { from: 20, to: 35, focus: [230, 350], zoom: 1.30, label: 'Image selection and inputs' },
  { from: 35, to: 52, focus: [240, 430], zoom: 1.34, label: 'Run analysis and fixture result' },
  { from: 52, to: 70, focus: [250, 430], zoom: 1.38, label: 'Score, action, and factors' },
  { from: 70, to: 90, focus: [1610, 500], zoom: 1.18, label: 'Queue and map' },
  { from: 90, to: 100, focus: [250, 450], zoom: 1.36, label: 'Inconclusive fixture' },
  { from: 100, to: 120, focus: [270, 430], zoom: 1.32, label: 'Critical mock fixture' },
  { from: 120, to: 139.48, focus: [960, 540], zoom: 1.0, label: 'Closing card' },
];

function wavSeconds(file) {
  const b = fs.readFileSync(file);
  return b.readUInt32LE(42) / b.readUInt32LE(28);
}
function num(n) { return Number(n.toFixed(6)); }

const durations = shots.map((_, i) => wavSeconds(path.join(__dirname, `paragraph-${String(i + 1).padStart(2, '0')}.wav`)));
const totalAudio = durations.reduce((a, b) => a + b, 0);
if (totalAudio > 150) throw new Error(`Narration is ${totalAudio.toFixed(3)}s, longer than the 150s picture.`);
const endHold = 150 - totalAudio;
const graph = [];

for (let i = 0; i < shots.length; i++) {
  const s = shots[i];
  const srcDuration = s.to - s.from;
  const outDuration = durations[i] + (i === shots.length - 1 ? endHold : transition);
  const speed = outDuration / srcDuration;
  const easeFrames = 72;
  const ease = `0.5-0.5*cos(PI*min(on/${easeFrames},1))`;
  const x = `max(0,min(iw-iw/zoom,(960+(${s.focus[0]}-960)*(${ease}))-iw/(2*zoom)))`;
  const y = `max(0,min(ih-ih/zoom,(540+(${s.focus[1]}-540)*(${ease}))-ih/(2*zoom)))`;
  const z = `1+(${s.zoom}-1)*(${ease})`;
  graph.push(`[0:v]trim=start=${s.from}:end=${s.to},setpts=(PTS-STARTPTS)*${num(speed)},fps=30,zoompan=z='${z}':x='${x}':y='${y}':d=1:s=1920x1080:fps=30,setsar=1,settb=AVTB[v${i}]`);
}

let current = 'v0';
let elapsed = durations[0] + transition;
for (let i = 1; i < shots.length; i++) {
  const offset = elapsed - (i * transition);
  const next = `xf${i}`;
  graph.push(`[${current}][v${i}]xfade=transition=fade:duration=${transition}:offset=${num(offset)}[${next}]`);
  current = next;
  elapsed += durations[i] + (i === shots.length - 1 ? endHold : transition);
}

const subtitleFilter = "subtitles=video_demo/production/captions.srt:force_style='FontName=Arial,FontSize=25,PrimaryColour=&H00FFFFFF,OutlineColour=&HAA061526,BorderStyle=3,BackColour=&H80061526,Outline=1,Shadow=0,Alignment=2,MarginV=54,WrapStyle=2'";
graph.push(`[${current}]${subtitleFilter},fps=30,format=yuv420p[vout]`);
graph.push(`[1:a]loudnorm=I=-16:TP=-1.5:LRA=7:print_format=summary[aout]`);
const complex = graph.join(';');

const args = [
  '-hide_banner', '-y', '-i', source, '-i', narration,
  '-filter_complex', complex,
  '-map', '[vout]', '-map', '[aout]', '-t', '150.000',
  '-r', '30', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
  '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', output,
];
const run = spawnSync(ffmpeg, args, { cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
process.stdout.write(run.stdout || '');
process.stderr.write(run.stderr || '');
if (run.error) throw run.error;
if (run.status !== 0) process.exit(run.status || 1);

const planLines = [
  '# Camera and scene plan',
  '',
  'Nine genuine dashboard capture ranges are matched to nine separately synthesized narration paragraphs. Each scene eases from the dashboard overview toward its stated focal area over 2.4 seconds, then holds. Adjacent scenes dissolve over 0.35 seconds.',
  '',
  '| Start | End | Capture range | Focus | Zoom |',
  '|---:|---:|---:|---|---:|',
];
let t = 0;
for (let i = 0; i < shots.length; i++) {
  const s = shots[i];
  const end = t + durations[i] + (i === shots.length - 1 ? endHold : 0);
  planLines.push(`| ${t.toFixed(2)} s | ${end.toFixed(2)} s | ${s.from}–${s.to} s | ${s.label} (${s.focus.join(', ')}) | ${s.zoom.toFixed(2)}× |`);
  t += durations[i];
}
planLines.push('', `Narration: ${totalAudio.toFixed(3)} s. Final-card hold after narration: ${endHold.toFixed(3)} s. Total output: 150.000 s.`);
fs.writeFileSync(path.join(__dirname, 'camera_plan.md'), planLines.join('\n') + '\n');
console.log(`Rendered ${output}; narration ${totalAudio.toFixed(3)}s; closing hold ${endHold.toFixed(3)}s.`);
