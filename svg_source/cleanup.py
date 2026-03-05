import xmltodict
import re


def parse_style(style_string):
    """
    Convert style="a:b;c:d" into dict {a:b, c:d}
    """
    result = {}
    if not style_string:
        return result

    parts = style_string.split(";")
    for part in parts:
        if ":" in part:
            key, value = part.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def clean_text_node(text_node):
    """
    Replace a messy <text> node with a clean one.
    """

    # Extract coordinates
    x = text_node.get("@x", "")
    y = text_node.get("@y", "")

    # Extract style values
    style_dict = parse_style(text_node.get("@style", ""))

    font_size = style_dict.get("font-size", "32px").replace("px", "")
    fill = style_dict.get("fill", "#000000")

    # Extract text content
    content = ""

    if "#text" in text_node:
        content = text_node["#text"]

    elif "tspan" in text_node:
        tspan = text_node["tspan"]

        if isinstance(tspan, list):
            content = "".join(
                t.get("#text", "") for t in tspan if isinstance(t, dict)
            )
        elif isinstance(tspan, dict):
            content = tspan.get("#text", "")

    # Build clean node
    clean_node = {
        "@x": x,
        "@y": y,
        "@font-family": "sans-serif",
        "@font-size": font_size,
        "@fill": fill,
        "#text": content.strip(),
    }

    return clean_node


def process_svg_dict(node):
    """
    Recursively walk SVG dict and clean all <text> elements.
    """
    if isinstance(node, dict):
        for key in list(node.keys()):

            # Match SVG namespace variations
            if key.endswith("text"):
                text_nodes = node[key]

                if isinstance(text_nodes, list):
                    node[key] = [clean_text_node(t) for t in text_nodes]
                else:
                    node[key] = clean_text_node(text_nodes)

            else:
                process_svg_dict(node[key])

    elif isinstance(node, list):
        for item in node:
            process_svg_dict(item)


def clean_svg(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        svg_dict = xmltodict.parse(f.read())

    process_svg_dict(svg_dict)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xmltodict.unparse(svg_dict, pretty=True))


if __name__ == "__main__":
    clean_svg("live_map_source_dark.svg", "live_map_source_dark_clean.svg")
