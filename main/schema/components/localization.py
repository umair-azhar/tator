localization_properties = {
    'x': {
        'description': 'Normalized horizontal position of left edge of bounding box for '
                       '`box` localization types, start of line for `line` localization '
                       'types, or position of dot for `dot` localization types.',
        'type': 'number',
        'minimum': 0.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'y': {
        'description': 'Normalized vertical position of top edge of bounding box for '
                       '`box` localization types, start of line for `line` localization '
                       'types, or position of dot for `dot` localization types.',
        'type': 'number',
        'minimum': 0.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'width': {
        'description': 'Normalized width of bounding box for `box` localization types.',
        'type': 'number',
        'minimum': 0.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'height': {
        'description': 'Normalized height of bounding box for `box` localization types.',
        'type': 'number',
        'minimum': 0.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'u': {
        'description': 'Horizontal vector component for `line` localization types.',
        'type': 'number',
        'minimum': -1.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'v': {
        'description': 'Vertical vector component for `line` localization types.',
        'type': 'number',
        'minimum': -1.0,
        'maximum': 1.0,
        'nullable': True,
    },
    'frame': {
        'description': 'Frame number of this localization if it is in a video.',
        'type': 'integer',
    },
    'parent': {
        'description': 'If a clone, the pk of the parent.',
        'type': 'number',
        'nullable': True,
    },
}

post_properties = {
    'media_id': {
        'description': 'Unique integer identifying a media.',
        'type': 'integer',
    },
    'type': {
        'description': 'Unique integer identifying a localization type.',
        'type': 'integer',
    },
    'version': {
        'description': 'Unique integer identifying the version.',
        'type': 'integer',
    },
    'modified': {
        'description': 'Whether this localization was created in the web UI.',
        'type': 'boolean',
        'nullable': True,
    },
}

localization_get_properties = {
    'id': {
        'type': 'integer',
        'description': 'Unique integer identifying this localization.',
    },
    'project': {
        'type': 'integer',
        'description': 'Unique integer identifying project of this localization.',
    },
    'meta': {
        'type': 'integer',
        'description': 'Unique integer identifying entity type of this localization.',
    },
    'media': {
        'type': 'integer',
        'description': 'Unique integer identifying media of this localization.',
    },
    'thumbnail_image': {
        'type': 'string',
        'description': 'URL of thumbnail corresponding to this localization.',
    },
    'modified': {
        'type': 'boolean',
        'description': 'Indicates whether this localization has been modified in the web UI.',
    },
    'version': {
        'type': 'integer',
        'description': 'Unique integer identifying a version.',
    },
    'email': {
        'type': 'string',
        'description': 'Email of last user who modified/created this localization.',
    },
    'attributes': {
        'description': 'Object containing attribute values.',
        'type': 'object',
        'additionalProperties': {'$ref': '#/components/schemas/AttributeValue'},
    },
    'created_datetime': {
        'type': 'string',
        'format': 'date-time',
        'description': 'Datetime this localization was created.',
    },
    'modified_datetime': {
        'type': 'string',
        'format': 'date-time',
        'description': 'Datetime this localization was last modified.',
    },
    'modified_by': {
        'type': 'integer',
        'description': 'Unique integer identifying the user who last modified this localization.'
    },
    'user': {
        'type': 'integer',
        'description': 'Unique integer identifying the user who created this localization.'
    }
}

localization_spec = {
    'type': 'object',
    'description': 'Localization creation spec. Attribute key/values must be '
                   'included in the base object.',
    'required': ['media_id', 'type', 'frame'],
    'additionalProperties': {'$ref': '#/components/schemas/AttributeValue'},
    'properties': {
        **post_properties,
        **localization_properties,
    },
}

localization_update = {
    'type': 'object',
    'properties': {
        **localization_properties,
        'attributes': {
            'description': 'Object containing attribute values.',
            'type': 'object',
            'additionalProperties': {'$ref': '#/components/schemas/AttributeValue'},
        },
        'modified': {
            'description': 'Whether this localization was created in the web UI.',
            'type': 'boolean',
            'nullable': True,
        },
    },
}

localization = {
    'type': 'object',
    'properties': {
        **localization_get_properties,
        **localization_properties,
    },
}

