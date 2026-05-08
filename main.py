from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'dock')

from ui.app import RowingApp

if __name__ == "__main__":
    RowingApp().run()
