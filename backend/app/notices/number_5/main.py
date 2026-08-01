import os
import glob

from . import SO_order as SO
from .varia import SO_list

from app.config import settings

# Written to a mounted volume, not into the image — see docker-compose.
OUT_DIR = settings.notice_output_dir


def main():
    if not SO_list:
        print("No SO numbers provided. Enter one SO number per line and run again.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)

    # Start clean so the dashboard's "Cards" list shows only this run's output.
    for old in glob.glob(os.path.join(OUT_DIR, "*card.png")):
        os.remove(old)
        print(f"cleared old card: {os.path.basename(old)}")

    print(f"Generating cards for {len(SO_list)} SO number(s)...")
    ok = 0
    failed = 0
    for so in SO_list:
        print("=" * 50)
        print(f"SO: {so}")
        try:
            SO.item_fetch(so)
            print("  card generated")
            ok += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("=" * 50)
    print(f"Done. {ok} card(s) generated, {failed} failed.")


if __name__ == "__main__":
    main()
