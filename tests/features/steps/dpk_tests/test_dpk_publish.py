import random

import behave


@behave.when(u'I publish a dpk to the platform')
def step_impl(context):
    context.dpk.name = context.dpk.name + str(random.randint(0, 1000000))
    context.published_dpk = context.project.dpks.publish(context.dpk)


@behave.then(u'The user defined properties should have the same values')
def step_impl(context):
    dpk = context.dpk
    p_dpk = context.published_dpk
    assert dpk.display_name == p_dpk.display_name
    assert dpk.version == p_dpk.version
    assert dpk.categories == p_dpk.categories
    assert dpk.icon == p_dpk.icon
    assert dpk.tags == p_dpk.tags
    assert dpk.scope == p_dpk.scope
    assert dpk.description == p_dpk.description
    assert dpk.components == p_dpk.components


@behave.then(u'id, name, createdAt, codebase, url and creator should have values')
def step_impl(context):
    dpk = context.published_dpk
    assert dpk.id is not None
    assert dpk.name is not None
    assert dpk.created_at is not None
    assert dpk.codebase is not None
    assert dpk.url is not None
