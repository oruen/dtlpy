from behave import given, then, when
import numpy as np
import dtlpy as dl


def mask_from_circle(h, w, center, radius):
    x, y = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)

    mask = dist_from_center <= radius
    return mask


@given(u'I have a segmentation annotation')
def step_impl(context):
    builder = context.item.annotations.builder()
    builder.add(
        annotation_definition=context.dl.Segmentation.from_polygon(
            geo=np.array([[100, 200], [150, 200], [300, 100], [200, 400]]),
            label='person',
            shape=(context.item.height, context.item.width)))
    annotations = builder.upload()
    context.annotation = annotations[0]


@given(u'I have a multi segmentation annotations')
def step_impl(context):
    builder = context.item.annotations.builder()

    mask1 = mask_from_circle(context.item.height, context.item.width, center=(200, 200), radius=100)
    mask2 = mask_from_circle(context.item.height, context.item.width, center=(400, 400), radius=100)
    mask = np.ma.mask_or(mask1, mask2)

    builder.add(annotation_definition=context.dl.Segmentation(mask, label='person'))
    annotations = builder.upload()
    context.annotation = annotations[0]


@when(u'I execute to_box function on segmentation annotation')
def step_impl(context):
    bbox = context.annotation.annotation_definition.to_box()
    builder = context.item.annotations.builder()
    builder.add(annotation_definition=bbox)
    annotations = builder.upload()
    context.bboxes = annotations


@when(u'I create Box annotation with  from_segmentation function with mask')
def step_impl(context):
    bbox = dl.Box.from_segmentation(context.annotation.annotation_definition.geo,
                                    context.annotation.label)
    builder = context.item.annotations.builder()
    builder.add(annotation_definition=bbox)
    annotations = builder.upload()
    context.bboxes = annotations


@then(u'Box will be generate')
def step_impl(context):
    should_be_geo = [[100, 100], [300, 400]]
    assert should_be_geo == context.bboxes[0].geo


@then(u'Boxes will be generate')
def step_impl(context):
    should_be_geo1 = [[100, 100], [300, 300]]
    should_be_geo2 = [[300, 300], [500, 500]]
    assert should_be_geo1 == context.bboxes[0].geo
    assert should_be_geo2 == context.bboxes[1].geo
