"""Tips page — dynamic recommendations based on usage patterns."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt5.QtCore import Qt
from claude_nagger.i18n import get_string as _t


class TipsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        header = QLabel(_t("tips_header"))
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        self.tips_layout = QVBoxLayout(container)
        self.tips_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def update_tips(self, stats, cost, subscription=None):
        # Clear old tips
        while self.tips_layout.count():
            item = self.tips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            from claude_nagger.core.tips import TipsEngine
            from claude_nagger.i18n import get_language
            import re

            lang = get_language()
            tips = TipsEngine.get_tips(stats, cost, subscription)

            cat_icons = {
                "cache": "\U0001f4be", "model": "\U0001f916", "session": "\u23f1",
                "prompt": "\u270d", "subscription": "\U0001f4b3",
                "skills": "\U0001f9e9", "docs": "\U0001f4d6",
            }

            for tip in tips:
                msg = tip.message_ua if lang == "ua" else tip.message_en
                # Make URLs clickable
                msg_html = re.sub(
                    r'(https?://\S+)',
                    r'<a href="\1" style="color: #000080;">\1</a>',
                    msg,
                )
                icon = cat_icons.get(tip.category, "\U0001f4a1")
                relevance_bar = "\u2588" * int(tip.relevance * 10) + "\u2591" * (10 - int(tip.relevance * 10))

                lbl = QLabel(
                    f'{icon}  <b>{tip.category.upper()}</b> '
                    f'<span style="color: #808080; font-size: 10px;">[{relevance_bar}]</span>'
                    f'<br/>{msg_html}'
                )
                lbl.setWordWrap(True)
                lbl.setOpenExternalLinks(True)
                lbl.setTextFormat(Qt.RichText)
                lbl.setStyleSheet(
                    "padding: 8px; margin: 2px 4px; background: white; color: #000; "
                    "border: 2px groove #808080; font-size: 12px;"
                )
                self.tips_layout.addWidget(lbl)

            if not tips:
                lbl = QLabel(_t("no_tips"))
                lbl.setStyleSheet("padding: 16px; color: #808080; font-style: italic;")
                self.tips_layout.addWidget(lbl)

        except ImportError:
            lbl = QLabel(_t("tips_require"))
            lbl.setStyleSheet("padding: 16px; color: #808080;")
            self.tips_layout.addWidget(lbl)
