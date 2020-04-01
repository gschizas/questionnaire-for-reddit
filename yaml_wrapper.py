import collections

from ruamel.yaml import YAML


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))


def literal_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data, style='|')
    else:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data)


def carry_over_compose_document(self):
    self.get_event()
    node = self.compose_node(None, None)
    self.get_event()
    # this prevents cleaning of anchors between documents in **one stream**
    # self.anchors = {}
    return node


def yaml():
    result = YAML()
    result.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor)
    result.add_representer(collections.OrderedDict, dict_representer)
    result.add_representer(str, literal_str_representer)
    result.composer.Composer.compose_document = carry_over_compose_document
    return result
