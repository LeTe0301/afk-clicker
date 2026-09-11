# AFK Farm Clicker

Autoclicker mit Spielerkennung und eigenen Einstellungen pro Spiel. Für
Minecraft mit Essenspause, weil Hard die einzige Schwierigkeit ist, auf der
Zombie-Reinforcements entstehen — und zugleich die einzige, auf der dich der
Hunger bis zum Tod runterzieht.

> **Versionierung:** Alles unter `1.0.0`. Oberfläche und das Format der
> gespeicherten Einstellungen bewegen sich noch; nach Semver ist `1.0.0` der
> Punkt, an dem sie das nicht mehr tun. Bis dahin wachsen nur Minor und Patch.

## Herunterladen

**[Releases](../../releases/latest)** → Archiv für dein System, entpacken,
starten. Kein Python nötig.

| System | Datei |
|---|---|
| Windows 10/11 | `AFK-Farm-Clicker-windows-x64.zip` |
| Linux (glibc 2.35+, X11) | `AFK-Farm-Clicker-linux-x86_64.tar.gz` |
| macOS (Apple Silicon) | `AFK-Farm-Clicker-macos-arm64.zip` |

Ab dann aktualisiert sich das Programm selbst: **Settings → Updates →
Check for updates**. Findet es ein neueres Release, lädt es das passende
Archiv, entpackt es daneben, beendet sich und tauscht sich aus. Der Tausch
läuft über ein kleines externes Skript — ein Programm kann seine eigene
laufende Datei nicht überschreiben, unter Windows schon gar nicht.

Liegt der Ordner an einem schreibgeschützten Ort (etwa `Program Files`), sagt
der Knopf das, statt es stumm zu versuchen.

### Was pro Plattform zu beachten ist

**Windows** — Defender schlägt womöglich an. Fehlalarm, und bei dieser
Programmart normal: ein globaler Tastatur-Hook plus synthetische Mausklicks ist
genau das Muster, nach dem die Heuristik sucht. Windows-Sicherheit → Viren- und
Bedrohungsschutz → Einstellungen verwalten → Ausschlüsse → Ordner hinzufügen.

**Linux** — braucht eine **X11**-Sitzung. Unter Wayland darf eine Anwendung
grundsätzlich keine Tasten sehen, die an andere Fenster gehen; das Fenster geht
auf, aber der Hotkey kann dort nicht funktionieren. Das Programm sagt das auch.

**macOS** — nicht signiert, erster Start also Rechtsklick → Öffnen. Danach unter
Systemeinstellungen → Datenschutz & Sicherheit → **Bedienungshilfen** freigeben,
sonst bleiben Hotkey und Klicks tot.

## Aufbau

Links die Spiele, rechts die Einstellungen des ausgewählten — wie in der
NVIDIA-App. Ein grüner Punkt heißt: läuft gerade. Taucht ein Spiel zum ersten
Mal auf, springt die Auswahl einmal dorthin; danach bleibt deine Wahl stehen,
statt sich alle fünf Sekunden selbst zu überschreiben.

**Jedes Spiel hat eigene Werte.** Intervall, Jitter, Auto-Stopp, Maustaste und
die Ess-Einstellungen werden pro Spiel gespeichert, in

| System | Ort |
|---|---|
| Windows | `%APPDATA%\AFKFarmClicker\settings.json` |
| Linux | `~/.config/afk-farm-clicker/settings.json` |
| macOS | `~/Library/Application Support/AFKFarmClicker/settings.json` |

**Add current game** legt aus dem gerade aktiven Fenster einen neuen Eintrag an.
Damit funktioniert die Erkennung für jedes Spiel, nicht nur für die
mitgelieferten — eingebaute Feinabstimmung gibt es nur für Minecraft, weil das
das einzige Spiel ist, für dessen Zahlen ich geradestehen kann.

Der **Hotkey gilt global**, für alle Spiele derselbe.

## Einstellungen

| Feld | Bedeutung |
|---|---|
| **Interval** | Abstand zwischen zwei Klicks. 650 ms deckt Javas volle Sword-Sweep-Aufladung ab (12 Ticks / 600 ms) plus einen Tick Puffer. |
| **Random jitter** | Streut das Intervall, damit der Rhythmus nicht exakt gleichmäßig ist. |
| **Auto-stop** | Hält nach N Minuten von selbst an. 0 heißt nie. |
| **Mouse button** | Links, rechts oder mittig. |
| **Pause & eat** | Klicken aussetzen, rechte Maustaste halten bis das Essen durch ist, weitermachen. Nur bei Linksklick sinnvoll, deshalb greift es auch nur dort. |
| **Hold RMB** | Rechte Maustaste dauerhaft halten. |
| **Eat every / Hold for** | Angreifen kostet ~1 Nahrungspunkt pro 20 s, verrottetes Fleisch gibt 4. Fleisch braucht 1,6 s — 2,0 s lässt Luft für einen verzögerten Tick. |

### Aussehen

Das Fenster übernimmt standardmäßig den hell/dunkel-Modus des Systems —
unter Windows, macOS und GNOME —, einmal beim Start gelesen. Unter
**Settings → Appearance** lässt es sich auf **Light** oder **Dark**
festlegen, oder wieder auf **System** zurückstellen — die Änderung wirkt
sofort, ohne Neustart. Auf anderen Linux-Desktops, oder wenn sich der
Systemwert gar nicht auslesen lässt, öffnet es sich bei **System** dunkel.

### Hotkey

**Record** drücken, bis zu **drei Tasten gleichzeitig** halten, loslassen — die
Aufnahme endet von selbst, es gibt keinen Bestätigungsknopf, nach dem man
während eines Akkords greifen müsste. Dann **Apply**.

Reihenfolge spielt keine Rolle, Modifier zählen zusätzlich. Ein Akkord feuert
einmal beim Zustandekommen, nicht wiederholt während er gehalten wird, und ein
Viertelsekunden-Debounce fängt Doppelanschläge ab.

Als Hotkey taugt jede Taste, aber eine **Funktionstaste ist die vernünftige
Wahl**: einen Buchstaben löst du beim Laufen versehentlich mit aus.

## Warum ein eigener Hotkey-Abgleich

Nicht `pynput.keyboard.GlobalHotKeys`. Das gleicht über `Listener.canonical()`
ab, was Zeichentasten durch das Tastaturlayout zurückführt — gemessen feuerte
damit jede benannte Taste und **keine einzige Zeichentaste**. Der Abgleich
passiert deshalb direkt auf dem rohen Ereignis, über Name, Zeichen *oder*
virtuellen Tastencode. Der Hotkey feuert damit auf der physischen Taste, die du
aufgenommen hast, und nicht auf dem, was diese Position nach einem
Layout-Wechsel bedeutet.

Nachgemessen mit synthetisierten Tastendrücken in `tests/test_chords_slow.py`:
**30 Akkord-/Modifier-Kombinationen** feuern genau einmal, **6 Beinahe-Treffer**
bleiben still, alle Permutationen eines Akkords zählen gleich, Halten löst
einmal aus. Abgedeckt sind Funktionstasten, Zeichentasten, das Metazeichen `+`
und Umlaute.

Die ursprüngliche Entwicklung lief über eine breitere Einmal-Messung — alle
ASCII-Zeichen, `< >` und Layouts von Polnisch bis Isländisch. Die ist nicht Teil
der Suite; hier stehen nur die Zahlen, die bei jedem Release tatsächlich
nachgefahren werden.

## Selbst bauen

Nicht nötig, wenn du das Release nimmst. Auf **Windows** `build.bat`
doppelklicken; braucht Python von python.org mit angehaktem „Add python.exe to
PATH". Auf Linux/macOS die Befehle aus `.github/workflows/release.yml`.

PyInstaller kann nicht cross-kompilieren — es friert den Interpreter ein, auf
dem es läuft. Jede Plattform muss auf sich selbst gebaut werden, daher die drei
Jobs im Workflow.

## Release bauen lassen

**Ein Tag veröffentlicht nichts mehr.** Releases laufen über einen
`release/{version}`-Branch:

```
git switch -c release/0.4.0
git push github release/0.4.0
```

Die Pipeline läuft dann in dieser Reihenfolge:

1. **Vollständige Testsuite**, inklusive des langsamen Tastendruck-Sweeps, den
   der PR-Durchlauf auslässt.
2. **Versionsabgleich** — schlägt fehl, wenn `__version__` im Code nicht zum
   Branchnamen passt. Eine Binärdatei, die eine falsche Version meldet, macht
   den eingebauten Updater dauerhaft blind für neue Versionen.
3. **Drei Builds** mit `--selftest` auf jeder Plattform.
4. **Manuelle Freigabe.** Die Pipeline hält an und wartet. Nichts landet ohne
   diesen Klick auf der Releases-Seite.
5. **Veröffentlichung** mit `SHA256SUMS`, getaggt auf genau dem Commit, der
   getestet wurde.

Das Gate ist ein GitHub-Environment namens `release` mit *Required reviewers*
(Settings → Environments). **Ohne dieses Environment läuft Schritt 4 einfach
durch** und die Freigabe existiert nur auf dem Papier.

Ohne Branch lässt sich der Workflow im Actions-Tab von Hand starten; die
Version wird dann abgefragt und auf `MAJOR.MINOR.PATCH` geprüft.

## Tests

```
xvfb-run -a python -m unittest discover -s tests -t .
```

Unter Linux braucht die Suite ein Display: pynput löst sein Backend beim Import
auf und scheitert ohne X-Server. Auf CI ist das ein Fehler, kein Grund zu
überspringen — die Suite bricht dort ab, statt „OK (skipped=57)" zu melden und
eine grüne Pipeline vorzutäuschen.

Der langsame Akkord-Sweep synthetisiert echte Tastendrücke und läuft nur mit
`AFK_SLOW_TESTS=1`.
