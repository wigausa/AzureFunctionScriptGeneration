import os


def load_template(template_name: str) -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(project_root, "templates", template_name)

    with open(template_path, "r", encoding="utf-8") as template_file:
        return template_file.read()
