import collections

import ruamel.yaml


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))


def literal_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data, style='|')
    else:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data)


class CarryOverComposer(ruamel.yaml.composer.Composer):
    def __init__(self, loader=None):
        super().__init__(loader=loader)

    def compose_document(self):
        # Drop the DOCUMENT-START event.
        self.parser.get_event()

        # Compose the root node.
        node = self.compose_node(None, None)

        # Drop the DOCUMENT-END event.
        self.parser.get_event()

        if not (hasattr(self, 'anchors') and getattr(self, 'anchors')):
            # noinspection PyAttributeOutsideInit
            self.anchors = {}
        return node


def _yaml():
    result = ruamel.yaml.YAML(typ='rt')
    result.constructor.add_constructor(ruamel.yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor)
    result.representer.add_representer(collections.OrderedDict, dict_representer)
    result.representer.add_representer(str, literal_str_representer)
    result.Composer = CarryOverComposer
    return result


yaml = _yaml()
