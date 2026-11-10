"""Start the MedClue app."""

import flet as ft

from medclue_mobile.app import MedClueApp


async def main(page: ft.Page) -> None:
    app = MedClueApp(page)
    await app.start()


if __name__ == "__main__":
    ft.run(main)
