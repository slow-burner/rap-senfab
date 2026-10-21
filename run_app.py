# -*- coding: utf-8 -*-
"""PyInstaller --onedir 로 묶인 exe 진입점. streamlit 서버를 띄운다."""

import os
import sys


def _base() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    from streamlit.web import cli as stcli

    app = os.path.join(_base(), "app.py")
    # config.ini 는 exe 폴더 옆에서 읽으므로 작업 디렉터리를 exe 위치로 둔다
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))

    sys.argv = [
        "streamlit", "run", app,
        "--global.developmentMode=false",
        "--client.toolbarMode=viewer",          # Deploy 메뉴 숨김
        "--browser.gatherUsageStats=false",
        "--server.port=8520",
        "--theme.base=light",
        "--theme.primaryColor=#12a37a",
        "--theme.backgroundColor=#eef0f2",
        "--theme.secondaryBackgroundColor=#f3f6f5",
        "--theme.textColor=#26332f",
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
