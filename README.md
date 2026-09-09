# AFK Farm Clicker

Autoclicker für die Drowned-/Kupfer-Reinforcement-Farm — mit Essenspause, weil
Hard die einzige Schwierigkeit ist, auf der Zombie-Reinforcements überhaupt
entstehen, und zugleich die einzige, auf der dich der Hunger bis zum Tod
runterzieht.

## Herunterladen

Fertige Windows-Version: **[Releases](../../releases/latest)** →
`AFK-Farm-Clicker-windows.zip` herunterladen, entpacken, `AFK Farm Clicker.exe`
starten. Kein Python nötig.

Den Ordner kannst du verschieben, wohin du willst — nur nicht die `.exe` allein
herausziehen, die Dateien daneben gehören dazu.

## Bedienung

1. **Record** klicken, gewünschte Taste drücken (Esc bricht ab).
2. **Apply** klicken — erst dann ist der Hotkey scharf.
3. Mit dem Hotkey startest und stoppst du den Clicker, auch während Minecraft
   im Vordergrund ist.

| Feld | Bedeutung |
|---|---|
| **Interval** | Abstand zwischen zwei Linksklicks. 510 ms ist Rays Works' Wert: schneller zerlegt den Sword-Sweep. |
| **Pause & eat** | Klicken aussetzen, rechte Maustaste halten bis das Essen durch ist, weitermachen. |
| **Hold RMB** | Rechte Maustaste dauerhaft halten (Blocken/Essen ohne Pause). |
| **Off** | Gar nicht essen. |
| **Eat every** | Abstand zwischen zwei Mahlzeiten. Angreifen kostet ~1 Nahrungspunkt pro 20 s, verrottetes Fleisch gibt 4. |
| **Hold for** | Wie lange die rechte Maustaste gehalten wird. Verrottetes Fleisch braucht 1,6 s — der Standardwert von 2,0 s lässt Luft für einen verzögerten Tick. |

### Warum Essen eine eigene Klickpause bekommt

Ein Linksklick bricht einen laufenden Essvorgang ab. Ein Autoclicker, der alle
~0,5 s angreift, würde das Essen also endlos neu starten und du würdest
trotzdem verhungern. Deshalb hört **Pause & eat** mit dem Klicken auf, hält
lange genug rechts, und macht danach weiter.

## Wenn Defender meckert

Fehlalarm, und bei dieser Programmart normal: ein globaler Tastatur-Hook plus
synthetische Mausklicks ist genau das Muster, nach dem die Heuristik sucht.
Windows-Sicherheit → Viren- und Bedrohungsschutz → Einstellungen verwalten →
Ausschlüsse → Ordner hinzufügen.

Der Build vermeidet die beiden schlimmsten Auslöser bereits: kein `--onefile`
(entpackt sich sonst bei jedem Start nach `%TEMP%`) und kein UPX.

## Administratorrechte

Meist **nicht nötig**. Unter Windows arbeitet die `keyboard`-Bibliothek ohne
erhöhte Rechte; sie werden erst gebraucht, wenn das Zielfenster selbst erhöht
läuft — was Minecraft üblicherweise nicht tut. Reagiert der Hotkey nicht,
während Minecraft im Vordergrund ist, baue mit `--uac-admin` neu.

## Selbst bauen

Nicht nötig, wenn du das Release nimmst. Sonst auf einem **Windows**-Rechner
(PyInstaller kann nicht cross-kompilieren):

```
build.bat
```

Braucht Python von python.org mit angehaktem „Add python.exe to PATH".

## Release bauen lassen

Die GitHub Action baut auf einem Windows-Runner und hängt die ZIP an ein
Release:

```
git tag v1.0.0
git push origin v1.0.0
```

Ohne Tag lässt sich der Workflow im Actions-Tab von Hand starten; das Ergebnis
liegt dann als Artifact statt als Release.

Die Action startet die gebaute .exe außerdem einmal kurz und prüft, dass sie
nicht sofort wieder beendet — ein fehlender Hidden-Import fällt sonst erst dem
ersten Nutzer auf, und ein Release, das niemand starten kann, ist schlimmer als
gar keins.
