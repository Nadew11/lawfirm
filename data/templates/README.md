# Data Templates for CMPM Validation

These CSV templates show the exact format the model expects for each data type.
Copy each template, replace the example rows with real data, and save to `../real/`.

## Required Files

### 1. `utility_bills.csv` (CRITICAL — needed for all buildings)
Monthly utility consumption for each building over 12-24 months.

| Column | Type | Description |
|--------|------|-------------|
| building | string | Must match config project key (e.g. `lab_ventilation`) |
| year | int | Calendar year |
| month | int | 1-12 |
| total_kwh | float | Total electricity consumption |
| demand_kw | float | Peak demand (optional, use 0 if unavailable) |
| gas_therms | float | Natural gas consumption (optional, use 0 if N/A) |
| total_cost | float | Total utility cost in dollars |

**Where to get it:** Utility portal export, or PDF bills (manually extract).
**Minimum:** 12 consecutive months per building. 24 months preferred.

### 2. `submeter_data.csv` (HIGH VALUE — for buildings with submeters)
Hourly or 15-minute interval submetered data.

| Column | Type | Description |
|--------|------|-------------|
| building | string | Must match config project key |
| timestamp | datetime | ISO format: `YYYY-MM-DD HH:MM` |
| heating_kw | float | Heating energy (kW) |
| cooling_kw | float | Cooling energy (kW) |
| lighting_kw | float | Lighting energy (optional, use 0) |
| plug_load_kw | float | Plug/misc loads (optional, use 0) |
| outdoor_temp_f | float | Outdoor temperature at timestamp (°F) |

**Where to get it:** BAS trend export (BACnet, Niagara, etc.)
**Minimum:** 6 months. 12 months preferred for full seasonal coverage.

### 3. `occupancy_schedule.csv` (IMPORTANT — improves baseline model)
Building occupancy patterns by day type and academic period.

| Column | Type | Description |
|--------|------|-------------|
| building | string | Must match config project key |
| day_type | string | `weekday`, `weekend`, or `holiday` |
| start_hour | int | 0-23, start of occupied period |
| end_hour | int | 0-23, end of occupied period |
| occupancy_fraction | float | 0.0-1.0 (1.0 = fully occupied) |
| period_start | date | YYYY-MM-DD, start of this schedule period |
| period_end | date | YYYY-MM-DD, end of this schedule period |

**Where to get it:** Class schedules, building manager, card swipe data.

### 4. `maintenance_log.csv` (FOR ELECTRICAL PROJECT)
Historical maintenance and failure records for electrical systems.

| Column | Type | Description |
|--------|------|-------------|
| date | date | YYYY-MM-DD |
| event_type | string | `routine_maintenance` or `major_failure` |
| system | string | System name (e.g. `electrical`) |
| description | string | Brief description |
| cost | float | Total cost in dollars |
| downtime_hours | int | Hours of building downtime |

**Where to get it:** CMMS export (Maximo, Corrigo, SchoolDude, etc.)
**Minimum:** 5 years of records. 10 years preferred.

## Weather Data

Weather data is **already downloaded** from NOAA for Chicago O'Hare (2024-2025).
If your campus is in a different climate zone, replace
`data/weather/hourly_weather.csv` with local data in the same format:

| Column | Type | Description |
|--------|------|-------------|
| year | int | Calendar year |
| month | int | 1-12 |
| day | int | 1-31 |
| hour | int | 0-23 |
| temp_c | float | Temperature in Celsius |
| temp_f | float | Temperature in Fahrenheit |

## Quick Start

```bash
# 1. Copy templates to real/ directory
cp data/templates/utility_bills.csv data/real/utility_bills.csv

# 2. Edit with your real data (keep the header row, replace example rows)

# 3. Run the model with real data
python3 run_real.py

# 4. Check outputs/ for results — files will be marked REAL or SYNTHETIC
```
