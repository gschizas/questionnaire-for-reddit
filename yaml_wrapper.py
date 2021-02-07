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


def carry_over_compose_document(self):
    # self.get_event()
    node = self.compose_node(None, None)
    # self.get_event()
    # this prevents cleaning of anchors between documents in **one stream**
    # self.anchors = {}
    return node


def _yaml():
    result = ruamel.yaml.YAML(typ='rt')
    result.constructor.add_constructor(ruamel.yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor)
    result.representer.add_representer(collections.OrderedDict, dict_representer)
    result.representer.add_representer(str, literal_str_representer)
    # result.Composer.compose_document = carry_over_compose_document
    return result


yaml = _yaml()
