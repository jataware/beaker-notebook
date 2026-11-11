from beaker_notebook.lib.app import BeakerApp


def test_page_stylesheet_does_not_fall_back_to_app_stylesheet():
    class ExampleApp(BeakerApp):
        slug = "stylesheet-test"
        stylesheet = "/assets/stylesheet-test/global.css"
        pages = {
            "notebook": {},
            "chat": {"stylesheet": "/assets/stylesheet-test/chat.css"},
        }

    config = ExampleApp().as_dict()

    assert config["stylesheet"] == "/assets/stylesheet-test/global.css"
    assert config["pages"]["notebook"]["stylesheet"] is None
    assert config["pages"]["chat"]["stylesheet"] == "/assets/stylesheet-test/chat.css"
