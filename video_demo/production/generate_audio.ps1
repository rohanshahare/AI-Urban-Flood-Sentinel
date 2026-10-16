param(
  [string]$OutFile = (Join-Path $PSScriptRoot 'narration.wav'),
  [string]$SrtFile = (Join-Path $PSScriptRoot 'captions.srt')
)
Add-Type -AssemblyName System.Speech
$ffmpeg = 'C:\Users\91888\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe'
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.SelectVoice('Microsoft Zira Desktop')
$voice.Rate = 1
$voice.Volume = 90
$voiceName = $voice.Voice.Name
$paragraphs = @((Get-Content (Join-Path $PSScriptRoot 'narration.txt') -Raw) -split '\r?\n\s*\r?\n' | Where-Object { $_.Trim() })
$allCues = [System.Collections.Generic.List[object]]::new()
$offset = 0.0
$totalSpoken = 0

for ($p = 0; $p -lt $paragraphs.Count; $p++) {
  $paragraph = $paragraphs[$p].Trim()
  $index = $p + 1
  $clip = Join-Path $PSScriptRoot ('paragraph-{0:D2}.wav' -f $index)
  $words = [System.Collections.Generic.List[object]]::new()
  $handler = [System.EventHandler[System.Speech.Synthesis.SpeakProgressEventArgs]]{
    param($sender, $event)
    $punctuation = ''
    $afterWord = $event.CharacterPosition + $event.CharacterCount
    while ($afterWord -lt $paragraph.Length -and [char]::IsPunctuation($paragraph[$afterWord])) {
      $punctuation += $paragraph[$afterWord]
      $afterWord++
    }
    $words.Add([pscustomobject]@{ Start=$event.AudioPosition.TotalSeconds; Text=$event.Text+$punctuation; SentenceEnd=($punctuation -match '[.!?]') })
  }
  $voice.add_SpeakProgress($handler)
  $voice.SetOutputToWaveFile($clip)
  $voice.Speak($paragraph)
  $voice.remove_SpeakProgress($handler)
  # PCM WAV duration is exact from its data size and the generated 22.05 kHz mono 16-bit format.
  $duration = ((Get-Item $clip).Length - 46) / 44100.0
  $lastWordStart = $words[$words.Count - 1].Start
  $mapScale = $duration / ($lastWordStart + 0.45)
  $group = [System.Collections.Generic.List[object]]::new()
  for ($i = 0; $i -lt $words.Count; $i++) {
    $group.Add($words[$i])
    if ($group.Count -ge 6 -or $words[$i].SentenceEnd -or $i -eq $words.Count - 1) {
      $start = $offset + $group[0].Start * $mapScale
      $last = $group[$group.Count - 1]
      $naturalEnd = if ($i -lt $words.Count - 1) { $offset + ($words[$i + 1].Start * $mapScale) - 0.05 } else { $offset + [Math]::Min($duration, ($last.Start + 0.72) * $mapScale) }
      $end = [Math]::Max($start + 0.3, [Math]::Min($naturalEnd, $offset + ($last.Start + 0.8) * $mapScale))
      $allCues.Add([pscustomobject]@{ Start=$start; End=$end; Text=(($group | ForEach-Object Text) -join ' ') })
      $group.Clear()
    }
  }
  $totalSpoken += $words.Count
  $offset += $duration
}
$voice.Dispose()

function Format-SrtTime([double]$Seconds) {
  $milliseconds = [int][Math]::Round($Seconds * 1000)
  $hours = [int][Math]::Floor($milliseconds / 3600000)
  $milliseconds %= 3600000
  $minutes = [int][Math]::Floor($milliseconds / 60000)
  $milliseconds %= 60000
  $seconds = [int][Math]::Floor($milliseconds / 1000)
  $milliseconds %= 1000
  '{0:00}:{1:00}:{2:00},{3:000}' -f $hours, $minutes, $seconds, $milliseconds
}
$lines = [System.Collections.Generic.List[string]]::new()
for ($i = 0; $i -lt $allCues.Count; $i++) {
  $lines.Add([string]($i + 1))
  $lines.Add("$(Format-SrtTime $allCues[$i].Start) --> $(Format-SrtTime $allCues[$i].End)")
  $lines.Add($allCues[$i].Text)
  $lines.Add('')
}
Set-Content -Path $SrtFile -Value $lines -Encoding utf8
Copy-Item -LiteralPath $SrtFile -Destination (Join-Path $PSScriptRoot '..\captions.srt') -Force
$list = Join-Path $PSScriptRoot 'paragraphs.ffconcat'
Set-Content $list "ffconcat version 1.0" -Encoding ascii
for ($p = 0; $p -lt $paragraphs.Count; $p++) { Add-Content $list ("file 'paragraph-{0:D2}.wav'" -f ($p + 1)) -Encoding ascii }
& $ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $list -c:a pcm_s16le $OutFile
$durationTotal = ($offset).ToString('F3', [Globalization.CultureInfo]::InvariantCulture)
Write-Output "Voice: $voiceName; spoken words: $totalSpoken; captions: $($allCues.Count); narration duration: $durationTotal seconds"
