def validate(context):
    return [] if context and context.snapshot else ["A canonical snapshot is required."]
