# AFK Farm Clicker

Autoclicker für die Drowned-/Kupfer-Reinforcement-Farm — mit Essenspause, weil
Hard die einzige Schwierigkeit ist, auf der Zombie-Reinforcements überhaupt
entstehen, und zugleich die einzige, auf der dich der Hunger bis zum Tod
runterzieht.

## Herunterladen

**[Releases](../../releases/latest)** → Archiv für dein System herunterladen,
entpacken, starten. Kein Python nötig.

| System | Datei |
|---|---|
| Windows 10/11 | `AFK-Farm-Clicker-windows-x64.zip` |
| Linux (glibc 2.35+, X11) | `AFK-Farm-Clicker-linux-x86_64.tar.gz` |
| macOS (Apple Silicon) | `AFK-Farm-Clicker-macos-arm64.zip` |

Den Ordner kannst du verschieben, wohin du willst — nur nicht die ausführbare
Datei allein herausziehen, die Dateien daneben gehören dazu.

### Was pro Plattform zu beachten ist

**Windows** — Defender schlägt womöglich an. Fehlalarm, und bei dieser
Programmart normal: ein globaler Tastatur-Hook plus synthetische Mausklicks ist
genau das Muster, nach dem die Heuristik sucht. Windows-Sicherheit → Viren- und
Bedrohungsschutz → Einstellungen verwalten → Ausschlüsse → Ordner hinzufügen.

**Linux** — braucht eine **X11**-Sitzung. Unter Wayland darf eine Anwendung
grundsätzlich keine Tasten sehen, die an andere Fenster gehen; das Fenster geht
auf, aber der Hotkey kann dort nicht funktionieren. Das Programm sagt das auch
statt stumm nichts zu tun.

**macOS** — nicht signiert, der erste Start braucht also Rechtsklick → Öffnen.
Danach unter Systemeinstellungen → Datenschutz & Sicherheit → **Bedienungshilfen**
freigeben, sonst bleiben Hotkey und Klicks tot.

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

Als Hotkey taugt jede Taste, aber eine **Funktionstaste ist die vernünftige
Wahl**: einen Buchstaben löst du beim Laufen versehentlich mit aus.

### Warum Essen eine eigene Klickpause bekommt

Ein Linksklick bricht einen laufenden Essvorgang ab. Ein Autoclicker, der alle
~0,5 s angreift, würde das Essen also endlos neu starten und du würdest
trotzdem verhungern. Deshalb hört **Pause & eat** mit dem Klicken auf, hält
lange genug rechts, und macht danach weiter.

## Warum ein eigener Hotkey-Abgleich

Das Programm benutzt nicht `pynput.keyboard.GlobalHotKeys`. Das gleicht Tasten
über `Listener.canonical()` ab, was Zeichentasten durch das Tastaturlayout
zurückführt — im Test feuerte damit **jede benannte Taste** (F1–F20, Home,
Space, Pfeile …) zuverlässig und **keine einzige Zeichentaste**. Der Abgleich
passiert deshalb direkt auf dem rohen Ereignis, über Zeichen *oder* virtuellen
Tastencode.

Das ist auch inhaltlich richtiger: Der Hotkey feuert dann auf der physischen
Taste, die du aufgenommen hast, und nicht auf dem, was diese Position nach
einem Layout-Wechsel bedeutet.

Nachgemessen mit synthetisierten Tastendrücken: 62 Kombinationen, darunter alle
Funktions- und Navigationstasten, sämtliche ASCII-Zeichen, die Metazeichen
`+ < >` und Zeichen aus deutschen, französischen, spanischen, nordischen,
polnischen, tschechischen, türkischen, ungarischen und isländischen Layouts —
alle feuern. Halten löst genau einmal aus, und `Strg+F6` reagiert weder auf
bloßes `F6` noch auf `Umschalt+F6`.

## Selbst bauen

Nicht nötig, wenn du das Release nimmst. Auf **Windows** `build.bat`
doppelklicken; braucht Python von python.org mit angehaktem „Add python.exe to
PATH". Auf Linux/macOS die Befehle aus `.github/workflows/release.yml`.

PyInstaller kann nicht cross-kompilieren — es friert den Interpreter ein, auf
dem es läuft. Jede Plattform muss auf sich selbst gebaut werden, deshalb die
drei Jobs im Workflow.

## Release bauen lassen

```
git tag v1.1.0
git push github v1.1.0
```

Baut alle drei Plattformen und hängt die Archive an ein Release. Ohne Tag
lässt sich der Workflow im Actions-Tab von Hand starten; das Ergebnis liegt
dann als Artifact.

Jeder Job startet die gebaute Anwendung anschließend mit `--selftest`, das
jeden verzögert aufgelösten Backend-Import anfasst. Ein fehlender
Hidden-Import fällt sonst nirgends auf: Eine `--windowed`-Anwendung hat keine
Konsole, es passiert einfach nichts — beim Nutzer, nach dem Release.
