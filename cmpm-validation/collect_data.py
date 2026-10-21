#!/usr/bin/env python3
"""Data Collection Helper — identifies exactly what data to request and from whom.

Run this to generate:
  1. A prioritized checklist of data requests
  2. Pre-written email templates for each data source
  3. A gap analysis showing what we have vs what we need

Usage:
    python3 collect_data.py              # full guide + email templates
    python3 collect_data.py --status     # show current data coverage
    python3 collect_data.py --emails     # just the email templates
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cmpm.config_loader import load_config
from cmpm.data_loader import discover_data

REAL_DIR = Path(__file__).resolve().parent / "data" / "real"
OUT = Path(__file__).resolve().parent / "outputs"

DEADLINE = date(2026, 10, 31)


def days_left() -> int:
    return (DEADLINE - date.today()).days


def check_status(cfg: dict) -> dict:
    """Check what real data files exist."""
    _, avail = discover_data(cfg)

    status = {
        "weather": avail.weather,
        "bills": {b: v for b, v in avail.bills.items()},
        "submeters": {b: v for b, v in avail.submeters.items()},
        "occupancy": {b: v for b, v in avail.occupancy.items()},
        "maintenance": avail.maintenance,
    }

    real_dir = Path(__file__).resolve().parent / "data" / "real"
    status["real_files"] = []
    if real_dir.exists():
        for f in sorted(real_dir.iterdir()):
            if f.is_file():
                status["real_files"].append((f.name, f.stat().st_size))

    return status


def generate_collection_guide(cfg: dict) -> str:
    """Generate the full data collection guide."""
    dl = days_left()
    projects = list(cfg["projects"].keys())
    project_names = {k: cfg["projects"][k]["name"] for k in projects}

    lines = []
    lines.append(f"# Campus Data Collection Guide")
    lines.append(f"## Deadline: October 31, 2026 ({dl} days from today)")
    lines.append("")
    lines.append("This guide tells you exactly what data to collect, who has it,")
    lines.append("how to ask for it, and in what format to deliver it.")
    lines.append("")

    # === PRIORITY 1: UTILITY BILLS ===
    lines.append("---")
    lines.append("## 1. UTILITY BILLS (Priority: CRITICAL)")
    lines.append("")
    lines.append("**What:** Monthly electricity and gas consumption for each building")
    lines.append("**Minimum:** 12 consecutive months per building")
    lines.append("**Ideal:** 24-36 months (shows trends, weather normalization)")
    lines.append("**Format:** CSV with columns: building, year, month, total_kwh, demand_kw, gas_therms, total_cost")
    lines.append("")
    lines.append("### Who Has This Data")
    lines.append("")
    lines.append("| Source | What They Have | How to Get It | Turnaround |")
    lines.append("|--------|---------------|---------------|------------|")
    lines.append("| **Utility company portal** (ComEd, Peoples Gas) | Monthly bills, 24+ months | Online CSV export from account portal | Immediate |")
    lines.append("| **Campus facilities/energy manager** | Aggregated bills, possibly by building | Email request | 1-3 days |")
    lines.append("| **Accounts payable / finance** | Payment records with costs | Email request | 3-5 days |")
    lines.append("| **Energy management system** (EnergyCAP, ENERGY STAR Portfolio Manager) | All of the above, already organized | Export from software | Immediate |")
    lines.append("")
    lines.append("### Buildings Needed")
    lines.append("")
    for pk in projects:
        lines.append(f"- **{pk}** ({project_names[pk]})")
    lines.append("")
    lines.append("### Fastest Path")
    lines.append("")
    lines.append("1. Check if the campus has **ENERGY STAR Portfolio Manager** — most universities do.")
    lines.append("   It already has all the bills organized by building. Export as CSV.")
    lines.append("2. If not, check **ComEd** (electricity) and **Peoples Gas** (gas) online portals.")
    lines.append("   Most allow CSV export of 24 months of billing history.")
    lines.append("3. If neither, ask the **energy manager** or **facilities director**.")
    lines.append("   They almost certainly track this in a spreadsheet or EMS.")
    lines.append("")

    # === PRIORITY 2: BAS/SUBMETER DATA ===
    lines.append("---")
    lines.append("## 2. SUBMETER / BAS TREND DATA (Priority: HIGH)")
    lines.append("")
    lines.append("**What:** Hourly or 15-min interval energy data broken out by heating, cooling, lighting")
    lines.append("**Minimum:** 6 months for 1 building (ideally the lab)")
    lines.append("**Format:** CSV with columns: building, timestamp, heating_kw, cooling_kw, lighting_kw, plug_load_kw, outdoor_temp_f")
    lines.append("")
    lines.append("### Who Has This Data")
    lines.append("")
    lines.append("| Source | What They Have | How to Get It | Turnaround |")
    lines.append("|--------|---------------|---------------|------------|")
    lines.append("| **Building Automation System (BAS)** | Real-time and historical trends | Trend export (Niagara, Tridium, Siemens, JCI) | Same day |")
    lines.append("| **BAS controls contractor** | Same data, may have remote access | Call/email with specific point list | 1-3 days |")
    lines.append("| **Campus energy dashboard** (if exists) | Pre-aggregated interval data | Export/download | Immediate |")
    lines.append("| **IoT/smart meters** (Lucid, EnerNOC, GridPoint) | Building-level interval | Platform export | Immediate |")
    lines.append("")
    lines.append("### What to Ask For")
    lines.append("")
    lines.append("Tell the BAS operator or controls contractor:")
    lines.append("")
    lines.append('> "I need trend data exported as CSV for the following BAS points,')
    lines.append('>  at hourly intervals, for the last 12 months:"')
    lines.append(">")
    lines.append("> - Main building electric meter (kW)")
    lines.append("> - Hot water / steam supply valve position or BTU meter (proxy for heating)")
    lines.append("> - Chilled water supply valve position or BTU meter (proxy for cooling)")
    lines.append("> - Lighting panel meter (if submetered)")
    lines.append("> - Outside air temperature (from BAS weather station or nearest sensor)")
    lines.append("")
    lines.append("### If No BAS or Submeters Exist")
    lines.append("")
    lines.append("The model still works — it just uses the synthetic submeter data.")
    lines.append("This is the **least critical** data type. Focus on utility bills first.")
    lines.append("")

    # === PRIORITY 3: OCCUPANCY ===
    lines.append("---")
    lines.append("## 3. OCCUPANCY SCHEDULES (Priority: MEDIUM)")
    lines.append("")
    lines.append("**What:** When each building is occupied and at what level")
    lines.append("**Format:** CSV with columns: building, day_type, start_hour, end_hour, occupancy_fraction, period_start, period_end")
    lines.append("")
    lines.append("### Who Has This Data")
    lines.append("")
    lines.append("| Source | What They Have | How to Get It | Turnaround |")
    lines.append("|--------|---------------|---------------|------------|")
    lines.append("| **Registrar / class scheduling** | Class times, room assignments | Export from scheduling system (Ad Astra, 25Live, etc.) | 1-3 days |")
    lines.append("| **Card access / security** | Door swipe counts by building, hour | Export from access control (CBORD, Lenel, etc.) | 2-5 days |")
    lines.append("| **Building manager** | Knows the actual hours from experience | Ask them to fill in the template | 1 day |")
    lines.append("| **Academic calendar** | Semester dates, breaks, holidays | University website | Immediate |")
    lines.append("")
    lines.append("### Quick Approximation")
    lines.append("")
    lines.append("If you can't get precise data, the building manager can fill in the template")
    lines.append("using their knowledge. You really only need:")
    lines.append("")
    lines.append("- What hours is the building open on weekdays?")
    lines.append("- What's the weekend usage like? (fraction of weekday)")
    lines.append("- When is the semester vs. summer vs. winter break?")
    lines.append("- What's the summer occupancy as a fraction of semester?")
    lines.append("")
    lines.append("### Key Dates to Capture")
    lines.append("")
    lines.append("| Period | Typical Dates | Typical Occupancy |")
    lines.append("|--------|--------------|-------------------|")
    lines.append("| Fall semester | Aug 25 – Dec 15 | 100% |")
    lines.append("| Winter break | Dec 16 – Jan 14 | 10-20% |")
    lines.append("| Spring semester | Jan 15 – May 10 | 100% |")
    lines.append("| Summer session | May 11 – Aug 24 | 20-40% |")
    lines.append("| Holidays | Various | 5-10% |")
    lines.append("")

    # === PRIORITY 4: MAINTENANCE ===
    lines.append("---")
    lines.append("## 4. MAINTENANCE / FAILURE RECORDS (Priority: MEDIUM — electrical project only)")
    lines.append("")
    lines.append("**What:** Historical work orders for electrical systems")
    lines.append("**Minimum:** 5 years of records")
    lines.append("**Format:** CSV with columns: date, event_type, system, description, cost, downtime_hours")
    lines.append("")
    lines.append("### Who Has This Data")
    lines.append("")
    lines.append("| Source | What They Have | How to Get It | Turnaround |")
    lines.append("|--------|---------------|---------------|------------|")
    lines.append("| **CMMS** (Maximo, Corrigo, TMA, SchoolDude/Brightly) | Full work order history | Export with filters: system=electrical | 1-3 days |")
    lines.append("| **Facilities director** | Knows major failures from memory | Interview + spreadsheet | 1 day |")
    lines.append("| **Insurance claims** | Major failure events with costs | Request from risk management | 5-10 days |")
    lines.append("| **Capital planning office** | Equipment age, replacement schedule | Request from facilities planning | 3-5 days |")
    lines.append("")
    lines.append("### What We Really Need")
    lines.append("")
    lines.append("For the electrical predictive monitoring project, the model needs:")
    lines.append("")
    lines.append("1. **How often do electrical failures happen?** (transformer, switchgear, breaker)")
    lines.append("2. **What does a failure cost?** (repair + downtime + emergency response)")
    lines.append("3. **What's the routine maintenance cost?** (annual PM, inspections, testing)")
    lines.append("")
    lines.append("Even rough answers from the facilities director are valuable:")
    lines.append("")
    lines.append('> "In the last 10 years, how many times has a transformer or main')
    lines.append('>  switchgear failed? What did it cost each time?"')
    lines.append("")

    # === DATA DELIVERY ===
    lines.append("---")
    lines.append("## 5. HOW TO DELIVER THE DATA")
    lines.append("")
    lines.append("```")
    lines.append("1. Copy the template:    cp data/templates/utility_bills.csv data/real/utility_bills.csv")
    lines.append("2. Replace example rows with real data (keep the header row)")
    lines.append("3. Run the model:        python3 run_real.py --check   (verify it found the data)")
    lines.append("4. Full run:             python3 run_real.py           (produces real_ prefixed outputs)")
    lines.append("```")
    lines.append("")
    lines.append("The model auto-detects files in `data/real/` and uses them where available,")
    lines.append("falling back to sampled Chicago buildings for anything missing.")
    lines.append("")
    lines.append("### Building Name Mapping")
    lines.append("")
    lines.append("The CSV `building` column must match these project keys exactly:")
    lines.append("")
    lines.append("| Project Key | Project Name | Building Type to Map |")
    lines.append("|-------------|-------------|---------------------|")
    for pk in projects:
        lines.append(f"| `{pk}` | {project_names[pk]} | Your corresponding building |")
    lines.append("")

    # === TIMELINE ===
    lines.append("---")
    lines.append(f"## 6. SUGGESTED COLLECTION TIMELINE ({dl} days left)")
    lines.append("")

    if dl > 10:
        lines.append(f"| Week | Action | Owner | Data Type |")
        lines.append(f"|------|--------|-------|-----------|")
        lines.append(f"| This week | Send utility bill requests (emails below) | You | Utility bills |")
        lines.append(f"| This week | Check ENERGY STAR Portfolio Manager access | Energy manager | Utility bills |")
        lines.append(f"| This week | Request BAS trend export from controls contractor | Facilities | Submeters |")
        lines.append(f"| This week | Get academic calendar dates for occupancy | Registrar website | Occupancy |")
        lines.append(f"| Day 3-5 | Receive utility bill exports, load into model | You | Bills |")
        lines.append(f"| Day 5-7 | Request CMMS export for electrical records | Facilities | Maintenance |")
        lines.append(f"| Day 7-10 | Run model with real bills, review results | You | All available |")
        lines.append(f"| Day 10-{dl} | Iterate: add more data, refine, present | You | Everything |")
    else:
        lines.append(f"**{dl} days is tight.** Focus on utility bills only — that's the highest-value data.")
        lines.append(f"Everything else can use the Chicago benchmarking samples.")

    lines.append("")

    return "\n".join(lines)


def generate_email_templates(cfg: dict) -> str:
    """Generate copy-paste email templates for data requests."""
    projects = list(cfg["projects"].keys())
    project_names = {k: cfg["projects"][k]["name"] for k in projects}
    building_list = "\n".join(f"  - {project_names[k]}" for k in projects)

    lines = []
    lines.append("# Email Templates for Data Requests")
    lines.append("")
    lines.append("Copy-paste these emails. Fill in the [bracketed] parts.")
    lines.append("")

    # Email 1: Energy Manager
    lines.append("---")
    lines.append("## Email 1: To Energy/Facilities Manager (SEND FIRST)")
    lines.append("")
    lines.append("**Subject:** Request for building energy data — campus modernization analysis")
    lines.append("")
    lines.append("```")
    lines.append("Hi [Name],")
    lines.append("")
    lines.append("I'm working on a campus modernization prioritization analysis and need")
    lines.append("monthly utility consumption data for the following buildings:")
    lines.append("")
    lines.append(building_list)
    lines.append("")
    lines.append("For each building, I need:")
    lines.append("  - Monthly electricity consumption (kWh) and peak demand (kW)")
    lines.append("  - Monthly natural gas consumption (therms), if applicable")
    lines.append("  - Monthly total utility cost ($)")
    lines.append("  - At least 12 months of data (24 months preferred)")
    lines.append("")
    lines.append("If you have this in ENERGY STAR Portfolio Manager, an export of the")
    lines.append("monthly consumption data would be perfect. Otherwise, a spreadsheet")
    lines.append("or CSV file works great.")
    lines.append("")
    lines.append("I also have a few quick questions:")
    lines.append("  1. Do any of these buildings have submetering or BAS trend logging?")
    lines.append("  2. Who is the BAS/controls contractor for these buildings?")
    lines.append("  3. Is there a CMMS system (Maximo, SchoolDude, etc.) with")
    lines.append("     maintenance history for the electrical distribution system?")
    lines.append("")
    lines.append(f"We're targeting October 31 for the analysis, so I'd appreciate")
    lines.append(f"getting the bill data within the next few days if possible.")
    lines.append("")
    lines.append("Thanks,")
    lines.append("[Your name]")
    lines.append("```")
    lines.append("")

    # Email 2: Utility Company
    lines.append("---")
    lines.append("## Email 2: To Utility Company (if no portal access)")
    lines.append("")
    lines.append("**Subject:** Historical consumption data request — [Account Number]")
    lines.append("")
    lines.append("```")
    lines.append("Hello,")
    lines.append("")
    lines.append("I'm requesting historical consumption data for the following")
    lines.append("service accounts associated with [University Name]:")
    lines.append("")
    lines.append("  Account: [account number]")
    lines.append("  Address: [service address]")
    lines.append("  Period: January 2024 through present")
    lines.append("")
    lines.append("I need monthly data including:")
    lines.append("  - Total consumption (kWh for electric, therms for gas)")
    lines.append("  - Peak demand (kW)")
    lines.append("  - Billed amount")
    lines.append("")
    lines.append("CSV or Excel format preferred. If available through your")
    lines.append("online portal, please let me know how to access it.")
    lines.append("")
    lines.append("This is for an internal energy analysis. I'm authorized to")
    lines.append("request this data as [your role] at [University Name].")
    lines.append("")
    lines.append("Thank you,")
    lines.append("[Your name]")
    lines.append("[Phone number]")
    lines.append("```")
    lines.append("")

    # Email 3: BAS Contractor
    lines.append("---")
    lines.append("## Email 3: To BAS/Controls Contractor")
    lines.append("")
    lines.append("**Subject:** BAS trend data export request — [Building Name]")
    lines.append("")
    lines.append("```")
    lines.append("Hi [Name],")
    lines.append("")
    lines.append("I need a trend data export from the BAS for [Building Name].")
    lines.append("")
    lines.append("Points needed (hourly intervals, last 12 months):")
    lines.append("  - Main building electric meter (kW)")
    lines.append("  - Hot water/steam supply BTU meter or valve position")
    lines.append("  - Chilled water supply BTU meter or valve position")
    lines.append("  - Lighting panel meter (if available)")
    lines.append("  - Outside air temperature sensor")
    lines.append("")
    lines.append("CSV format preferred, with timestamps in the first column.")
    lines.append("")
    lines.append("If you can also export the BAS schedule for this building")
    lines.append("(occupied/unoccupied times), that would be very helpful.")
    lines.append("")
    lines.append("Thanks,")
    lines.append("[Your name]")
    lines.append("```")
    lines.append("")

    # Email 4: CMMS
    lines.append("---")
    lines.append("## Email 4: To Facilities/Maintenance Manager (for electrical project)")
    lines.append("")
    lines.append("**Subject:** Historical electrical maintenance records request")
    lines.append("")
    lines.append("```")
    lines.append("Hi [Name],")
    lines.append("")
    lines.append("For the campus modernization analysis, I need historical work order")
    lines.append("data for electrical distribution equipment. Could you export from")
    lines.append("[CMMS system name] the following:")
    lines.append("")
    lines.append("  - All work orders where system = electrical (or similar filter)")
    lines.append("  - Date range: last 5-10 years")
    lines.append("  - Include: date, work type (PM vs corrective), description,")
    lines.append("    actual cost, and any downtime hours")
    lines.append("")
    lines.append("I'm specifically interested in:")
    lines.append("  - Any transformer, switchgear, or breaker failures")
    lines.append("  - Total cost of each major incident (parts + labor + emergency)")
    lines.append("  - How many hours each building was without power")
    lines.append("")
    lines.append("If a CMMS export isn't easy, even a rough summary would help:")
    lines.append("  - How many major electrical failures in the last 10 years?")
    lines.append("  - Approximate cost of each?")
    lines.append("  - Current age of main transformers and switchgear?")
    lines.append("")
    lines.append("Thanks,")
    lines.append("[Your name]")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def print_status(cfg: dict) -> None:
    """Print current data coverage status."""
    status = check_status(cfg)
    dl = days_left()

    print(f"\n{'='*60}")
    print(f"DATA COLLECTION STATUS — {dl} days to deadline")
    print(f"{'='*60}")

    print(f"\nWeather:     {'HAVE IT (NOAA ISD)' if status['weather'] else 'MISSING'}")
    print(f"Maintenance: {'HAVE IT' if status['maintenance'] else 'NEED IT'}")
    print()

    print("Building Data:")
    print(f"{'Building':<25} {'Bills':>8} {'Submeter':>10} {'Occupancy':>10}")
    print("-" * 55)
    for bldg in status["bills"]:
        b = "HAVE" if status["bills"].get(bldg) else "NEED"
        s = "HAVE" if status["submeters"].get(bldg) else "NEED"
        o = "HAVE" if status["occupancy"].get(bldg) else "NEED"
        print(f"{bldg:<25} {b:>8} {s:>10} {o:>10}")

    have = sum(1 for v in status["bills"].values() if v)
    total = len(status["bills"])
    print(f"\nBill coverage: {have}/{total} buildings")

    if status["real_files"]:
        print("\nFiles in data/real/:")
        for name, size in status["real_files"]:
            print(f"  {name} ({size:,} bytes)")
    else:
        print("\nNo files in data/real/ yet.")

    print(f"\nNext step: Run `python3 collect_data.py` for the full collection guide.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Data Collection Helper")
    parser.add_argument("--status", action="store_true", help="Show current data coverage")
    parser.add_argument("--emails", action="store_true", help="Just the email templates")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    cfg = load_config()

    if args.status:
        print_status(cfg)
        return

    if args.emails:
        emails = generate_email_templates(cfg)
        print(emails)
        out_path = OUT / "data_collection_emails.md"
        out_path.write_text(emails)
        print(f"\nSaved to {out_path}")
        return

    # Full guide
    guide = generate_collection_guide(cfg)
    emails = generate_email_templates(cfg)
    full = guide + "\n\n" + emails

    print(full)

    out_path = OUT / "data_collection_guide.md"
    out_path.write_text(full)
    print(f"\n{'='*60}")
    print(f"Full guide saved to: {out_path}")
    print(f"Email templates saved to: {OUT / 'data_collection_emails.md'}")

    (OUT / "data_collection_emails.md").write_text(emails)


if __name__ == "__main__":
    main()
