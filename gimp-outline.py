#!/usr/bin/env python

# docs: https://www.gimp.org/docs/python/index.html
# 
# Based on a similar plugin by Pete Nu
#     http://pete.nu/software/gimp-outliner/
#
# Improvements:
#     * works inside layer groups
#     * [planned] provides outlines for all layers in a group
#       on a single layer

from gimpfu import *

#
#
#  L A Y E R   M A N A G E M E N T
#
# todo: spin layer stuff into a separate file, because autobubble also uses 
# this very same code. This means this and autobubble script may share certain
# bugs as well

# get the type we want for our layer
def get_layer_type(image):
  if image.base_type is RGB:
    return RGBA_IMAGE
  return GRAYA_IMAGE


# finds layer position in a layer group
def get_layer_stack_position(layer, group):
  iterator_pos = 0

  if type(group) is tuple:
    for layer_id in group:
      if gimp.Item.from_id(layer_id) == layer:
        return iterator_pos
      iterator_pos = iterator_pos + 1
  else:
    for l in group:
      if l == layer:
        return iterator_pos
      iterator_pos = iterator_pos + 1

  return 0  # for some reason we didn't find proper position of layer in the stack     


# add a new layer under given layer
def add_layer_below(image, layer):
  stack_pos = 0
  
  if layer.parent:
    # parent is a group layer (= we're inside a group layer)
    # this returns a tuple: (parent id, (<child ids>)). We want child ids.
    sublayers = pdb.gimp_item_get_children(layer.parent)[1]
    stack_pos = get_layer_stack_position(layer, sublayers)
  else:
    # parent is not a group layer (e.g. selected layer is on top level)
    stack_pos = get_layer_stack_position(layer, image.layers)
  
  layer_out = gimp.Layer(image, "outline::{}".format(layer.name), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer.parent, stack_pos + 1)

  return layer_out


# adds layer at the bottom of a given group
def add_layer_group_bottom(image, layer):
  stack_pos = 0
  
  if type(layer) is gimp.GroupLayer:
    # we want to give outline to a layer group. We add new layer at 
    # at the bottom of the current group, so moving the group moves
    # both group's original contents as well as the outline
    stack_pos = len(pdb.gimp_item_get_children(layer)[1]) - 1

  else:
    # not a layer group, business as usual:
    return add_layer_below(image, layer)
  
  layer_out = gimp.Layer(image, "outline::{}".format(layer.name), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer, stack_pos + 1)

  return layer_out




#
#
# O U T L I N E   F U N C T I O N S 
#

def clear_selection(image):
  pdb.gimp_image_select_rectangle(image, CHANNEL_OP_SUBTRACT, 0, 0, image.width,image.height)


def create_selection(image, layer, thickness, feather):
	# Select the text
	pdb.gimp_selection_layer_alpha(layer)
	
	# Grow the selection
	pdb.gimp_selection_grow(image, thickness)
	
	# Feather it
	if (feather > 0):
		pdb.gimp_selection_feather(image, feather)		


def paint_selection(layer):
  pdb.gimp_edit_bucket_fill_full(layer, BUCKET_FILL_BG, LAYER_MODE_NORMAL, 100, 0, 0, 1, 0, 1, 1)


#
#
# L A Y E R   H A N D L I N G
#

def outline_layer_group(image, group_layer, thickness, feather, separate_groups, separate_layers, merge_source_layer):
  # if we're separating groups, we put a new layer at the 
  # buttom of our layer group

  sublayers = pdb.gimp_item_get_children(group_layer)[1]

  # If we're using this function, there's about two valid options:
  #   A) we use separate layers for separate groups
  #   B) we want to use a separate layer for every layer
  # Each option requires a slightly different approach.

  if separate_groups:
    group_layers = []
    for layerId in sublayers:
      layer = gimp.Item.from_id(layerId)

      # we ignore hidden layers
      if not layer.visibility:
        continue

      # we hide layer gropups and put them on a "handle me later pls" list
      if type(layer) is gimp.GroupLayer:
        group_layers.append(layer)
        layer.visibility = False
      # we don't separate layers, so we don't do anything with things that 
      # aren't layer groups.

    # we do outline of the current layer group
    group_outline_layer = add_layer_group_bottom(image, group_layer)
    paint_selection(group_outline_layer)
    clear_selection(image)

    # now it's recursion o'clock:
    # (and yes, we do recursion)
    for layer in group_layers:
      layer.visibility = True
      outline_layer_group(image, layer, thickness, feather, separate_groups, separate_layers, merge_source_layer)
  
  else: 
    # so we're doing this layer by layer, possibly even separating layers
    for layerId in sublayers:
      layer = gimp.Item.from_id(layerId)

      # we ignore hidden layers
      if not layer.visibility:
        continue
      
      if type(layer) is gimp.GroupLayer:
        # yes, we do recursion
        outline_layer_group(image, layer, thickness, feather, separate_groups, separate_layers, merge_source_layer)
      else:
        create_selection(image, layer, thickness, feather)

        if separate_layers:
          outline_layer = add_layer_below(image, layer)
          paint_selection(outline_layer)
          
          if merge_source_layer: 
            name = layer.name         # save name of original layer
            merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
            merged_layer.name = name  # restore name of original layer

          clear_selection(image)

# main function
def python_outline(image, drawable, color, thickness, feather, separate_groups, separate_layers, merge_source_layer):
  bg_save = gimp.get_background()
  clear_selection(image)
  layer = image.active_layer
  gimp.set_background(color)

  # we ignore hidden layers
  if not layer.visibility:
    continue
  
  # we only do recursion if layers or groups have separate outlines
  # but we don't do recursion on 'merge source layer' and 'not separate layers'
  # because if we're merging source layer when group layer is selected, the entire
  # group is getting merged down to the outline. That makes everything pointles.
  # 
  # also yes, btw, we can merge layer group to a layer below the group
  # we can also create selection from layer group alpha, which saves us some work
  recursive = (separate_groups or separate_layers) and not (merge_source_layer and not separate_groups)

  if type(layer) is gimp.GroupLayer and recursive:
    outline_layer_group(image, layer, thickness, feather, separate_groups, separate_layers, merge_source_layer)

    # if we separated layers or groups, outlines are already filled with color, so 
    # we can skip that part
    if type(layer) is gimp.GroupLayer and not separate_layers and not separate_groups:
      group_outline_layer = add_layer_group_bottom(image,layer)
      paint_selection(group_outline_layer)
  else:
    create_selection(image, layer, thickness, feather)
    outline_layer = add_layer_below(image, layer)
    paint_selection(outline_layer)
    
    if merge_source_layer:
      name = layer.name         # save name of original layer
      merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
      merged_layer.name = name  # restore name of original layer
    
  # clear selection and restore background color
  clear_selection(image)
  gimp.set_background(bg_save)


def test_outline(image, thickness, feather, separate_groups, separate_layers, merge_source_layer):
  clear_selection(image)
  layer = image.active_layer

  # we only do recursion if we separate layers or groups. Also 'merge source layer'
  # option is really only valid with separate layers, because if groups are allowed
  # to get merged, everything is a bit pointless. 
  # 
  # also yes, btw, we can merge layer group to a layer below the group
  # we can also create selection from layer group alpha, which saves us some work
  recursive = (separate_groups and not merge_source_layer) or separate_layers

  if type(layer) is gimp.GroupLayer and recursive:
     outline_layer_group(image, layer, thickness, feather, separate_groups, separate_layers, merge_source_layer)
    # if we separated layers or groups, outlines are already filled with color, so 
    # we can skip that part
    if type(layer) is gimp.GroupLayer and not separate_layers and not separate_groups:
      group_outline_layer = add_layer_group_bottom(image,layer)
      paint_selection(group_outline_layer)

  else:
    create_selection(image, layer, thickness, feather)
    outline_layer = add_layer_below(image, layer)
    paint_selection(outline_layer)
    
    if merge_source_layer:
      name = layer.name         # save name of original layer
      merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
      merged_layer.name = name  # restore name of original layer
    
  # clear selection and restore background color
  clear_selection(image)