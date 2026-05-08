from kivy.config import Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '768')
Config.set('graphics', 'fullscreen', 'auto')

from ui.app import RowingApp

if __name__ == "__main__":
    RowingApp().run()
