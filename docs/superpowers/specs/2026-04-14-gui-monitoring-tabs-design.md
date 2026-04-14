# GUI Monitoring Tabs — Design Spec

**Дата:** 2026-04-14
**Проект:** fart-run-awesome-hasselhoff (ex claude-nagger + claude-monitor)

## Огляд

Додати 3 нових таби в існуючий PyQt5 GUI (NaggerDashboard, Win95 стиль):
- Docker Monitor
- Port/Service Map
- Security Scan

Реюз існуючих collectors з `plugins/`. Алерти через NaggerPopup + пердежі.

## Архітектура

Нові GUI таби — окремі файли в `gui/`:
```
gui/
├── docker_tab.py      # DockerTab(QWidget)
├── ports_tab.py       # PortsTab(QWidget)
├── security_tab.py    # SecurityTab(QWidget)
└── monitor_alerts.py  # MonitorAlertManager — мост між collectors і NaggerPopup
```

Кожен таб:
- Наслідує QWidget
- Має `update_data()` метод який викликається по QTimer
- Використовує QTableWidget в Win95 стилі
- Реюзає collectors напряму (не через SQLite — GUI працює синхронно)

## Docker Tab

**Таблиця:** NAME | STATUS | CPU% | RAM | PORTS | HEALTH
- Рядки кольорові: зелений status=running, сірий=exited, червоний=high CPU/RAM
- Іконки: ● running, ○ exited, ◉ warning
- CPU/RAM як progress bars в клітинках (Win95 inset стиль)

**Events panel:** QGroupBox внизу з останніми 10 подіями (start/stop/crash)

**Data source:** `plugins.docker_monitor.collector.collect_containers()`

## Ports Tab

**Таблиця:** PORT | PROTO | PROCESS | CONTAINER | PROJECT | STATUS
- Конфлікти — червоний рядок з іконкою ⚠
- Exposed (0.0.0.0) — жовтий маркер

**Summary:** QLabel внизу — "N ports | M conflicts | K exposed"

**Data source:** `plugins.port_map.collector.collect_ports()`

## Security Tab

**Header:** 4 severity counters (CRIT/HIGH/MED/LOW) як QLabels з кольоровим background

**Таблиця:** SEV | TYPE | DESCRIPTION | SOURCE
- Sorted by severity (critical first)
- Severity кольори: червоний/оранжевий/жовтий/сірий

**Кнопка:** "Scan Now" — запускає повний скан

**Data sources:** всі `scan_*()` з `plugins.security_scan.scanners`

## Алерти

`MonitorAlertManager` — обгортка над існуючим NaggerPopup:
- Приймає Alert objects з collectors
- Дедуплікація (як в core/alerts.py)
- Critical → NaggerPopup + гучний пердіж
- Warning → NaggerPopup + тихий пердіж
- Quiet hours з конфігу

## Timers

- Docker + Ports: кожні 5 сек (QTimer)
- Security: кожну годину або по кнопці "Scan Now"

## Entry Points

- `dev-monitor` — TUI (Textual), як зараз
- `dev-monitor-gui` — PyQt5 GUI

## .desktop файл

```ini
[Desktop Entry]
Name=Fart Run & Awesome Hasselhoff
Comment=Dev environment monitor with fart-powered alerts
Exec=python3 -m gui.app
Path=/home/dchuprina/claude-monitor
Icon=/home/dchuprina/claude-monitor/assets/icon.png
Terminal=false
Type=Application
Categories=Development;
```

## Залежності (додаткові)

```
PyQt5>=5.15
```
