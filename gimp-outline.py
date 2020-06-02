#!/usr/bin/env python

# docs: https://www.gimp.org/docs/python/index.html
#
# (c) Tamius Han, 2020. 
# website: https://tamius.net
# github:  https://github.com/tamius-han
#  
# Based on a similar plugin by Pete Nu
#     http://pete.nu/software/gimp-outliner/
#
# Improvements:
#     * works inside layer groups
#     * provides outlines for all layers in a group
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
def add_layer_below(image, layer, preserveCmd=False, argumentPass='()=>skip'):
  stack_pos = 0
  
  if layer.parent:
    # parent is a group layer (= we're inside a group layer)
    # this returns a tuple: (parent id, (<child ids>)). We want child ids.
    sublayers = pdb.gimp_item_get_children(layer.parent)[1]
    stack_pos = get_layer_stack_position(layer, sublayers)
  else:
    # parent is not a group layer (e.g. selected layer is on top level)
    stack_pos = get_layer_stack_position(layer, image.layers)
  
  if preserveCmd:
    new_name = layer.name
  else:
    new_name = layer.name.split('()=>')[0]

  layer_out = gimp.Layer(image, "outline::{}{}".format(new_name, argumentPass), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer.parent, stack_pos + 1)

  return layer_out


# adds layer at the bottom of a given group
def add_layer_group_bottom(image, layer, preserveCmd=False, argumentPass='()=>skip'):
  stack_pos = 0
  
  if type(layer) is gimp.GroupLayer:
    # we want to give outline to a layer group. We add new layer at 
    # at the bottom of the current group, s o moving the group moves
    # both group's original contents as well as the outline
    stack_pos = len(pdb.gimp_item_get_children(layer)[1]) - 1

  else:
    # not a layer group, business as usual:
    return add_layer_below(image, layer)
  
  if preserveCmd:
    new_name = layer.name
  else:
    new_name = layer.name.split('()=>')[0]

  layer_out = gimp.Layer(image, "outline::{}{}".format(new_name, argumentPass), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer, stack_pos + 1)

  return layer_out

#
#
#  C O L O R    S T A C K
#

__saved_colors_bg = []
__saved_colors_fg = []
def color_push_bg(color):
  __saved_colors_bg.append(color)

def color_pop_bg():
  return __saved_colors_bg.pop()

def color_push_fg(color):
  __saved_colors_fg.append(color)

def color_pop_fg():
  return __saved_colors_fg.pop()

def set_bg_stack(newColor):
  color_push_bg(gimp.get_background())
  gimp.set_background(newColor)

def restore_bg_stack():
  gimp.set_background(color_pop_bg())

def set_fg_stack(newColor):
  color_push_fg(gimp.get_foreground())
  gimp.set_foreground(newColor)

def restore_fg_stack():
  gimp.set_foreground(color_pop_fg())

#
#
#  A U T O - A R G U M E N T     P A R S E R
#
# yes, we'll parse arguments from layers. 

def parse_args_from_layer_name(name):
  firstCommand = name.split('>>')[0]
  if firstCommand.find('()=>skip') != -1:
    return [['skip']]
  if firstCommand.find('()=>end') != -1:
    return [['end']]

  argLine = firstCommand.split('()=>outline')[1].split('()=>')[0]
  argsIn = argLine.split(' ')

  argsOut = []

  for arg in argsIn:
    argsOut.append(arg.split('='))


  argPassAll = "()=>outline".join(name.split('()=>outline')[1:]).split('>>')
  argPassCount = len(argPassAll)

  if argPassCount > 1:
    argPass = '>>'.join(argPassAll[1:])
    argsOut.append(['pass', argPass])

  return argsOut


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

def outline_layer_group(image, group_layer, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer):
  # in auto mode, we parse arguments from layer name
  skip = False
  argPass = '()=>skip'
  preserveCmd = False

  isGroupLayer = type(group_layer) is gimp.GroupLayer

  sublayers = []
  if isGroupLayer:
   sublayers = pdb.gimp_item_get_children(group_layer)[1]


  if auto:
    try: 
      arguments = parse_args_from_layer_name(group_layer.name)
      for arg in arguments:
        if arg[0] == 'end':
          return
        if arg[0] == 'skip':
          if isGroupLayer:
            skip = True
          else:
            return
          break
        if arg[0] == 't':
          thickness = int(arg[1])
        elif arg[0] == 'f':
          feather = int(arg[1])
        elif arg[0] == 'separate_groups':
          separate_groups = True
          separate_layers = False
        elif arg[0] == 'separate_layers':
          separate_groups = False
          separate_layers = True
        elif arg[0] == 'no_separate_groups':
          separate_groups = False
        elif arg[0] == 'no_separate_layers':
          separate_layers = False
        elif arg[0] == 'merge_source':
          merge_source_layer = True
        elif arg[0] == 'no_merge_source':
          merge_source_layer = False
        elif arg[0] == 'color':
          color = arg[1]
        elif arg[0] == 'pass':
          argPass = arg[1]
        elif arg[0] == 'no_default_skip':
          argPass = ''
        elif arg[0] == 'preserve_cmd':
          preserveCmd = True
      


      if arguments and inherit_auto_config:
        use_defaults = True
      elif not arguments and not use_defaults:
        skip = True

    except:
      if not use_defaults:
        print("No command in layer name, will skip")
        print(group_layer.name)
        if isGroupLayer:
          skip = True
        else:
          return


  
  if color:
      set_bg_stack(color)

  if not isGroupLayer:
    create_selection(image, group_layer, thickness, feather)
    outline_layer = add_layer_below(image, group_layer, preserveCmd, argPass)
    paint_selection(outline_layer)
  else:
    # If we're using this function, there's about two valid options:
    #
    #   A) we use separate layers for separate groups
    #   A.2) we use one layer for layer group and its descendants
    #   B) we want to use a separate layer for every layer
    #
    # Each option requires a slightly different approach.
    # A.2 -- which happens when both separate_groups and separate_layers
    # are false -- is a mild variation on scenario A, hence this condition:

    if separate_groups or not separate_layers:
      group_layers = []
      for layerId in sublayers:
        layer = gimp.Item.from_id(layerId)

        # we ignore hidden layers
        if not layer.visible:
          continue

        # we hide layer gropups and put them on a "handle me later pls" list
        # in case of A.2, we skip this step
        if type(layer) is gimp.GroupLayer and separate_groups:
          group_layers.append(layer)
          layer.visible = False
        # we don't separate layers, so we don't do anything with things that 
        # aren't layer groups.

      # we do outline of the current layer/layer group group.
      # we also do this when separate_groups and separate_layers are both false
      if not skip:
        group_outline_layer = add_layer_below(image, group_layer, preserveCmd, argPass)
        paint_selection(group_outline_layer)
        clear_selection(image)

      # now it's recursion o'clock:
      # (and yes, we do recursion)
      # unless we use scenario A.2
      if separate_groups:
        for layer in group_layers:
          layer.visible = True
          outline_layer_group(image, layer, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer)
    
    else: 
      # so we're doing this layer by layer, possibly even separating layers
      for layerId in sublayers:
        layer = gimp.Item.from_id(layerId)

        # we ignore hidden layers
        if not layer.visible:
          continue
        
        # yes, we do recursion
        # btw we do this to paint outline as well. Layer groups aren't the only
        # layer objects that can contain a command
        outline_layer_group(image, layer, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer)
        
        
        if merge_source_layer: 
          name = layer.name         # save name of original layer
          merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
          merged_layer.name = name  # restore name of original layer

        clear_selection(image)
  
  if color:
    restore_bg_stack()

# main function
def test_outline(image, drawable, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer):
  clear_selection(image)
  layer = image.active_layer

  # we only do recursion if we separate layers or groups. Also 'merge source layer'
  # option is really only valid with separate layers, because if groups are allowed
  # to get merged, everything is a bit pointless. 
  # 
  # also yes, btw, we can merge layer group to a layer below the group
  # we can also create selection from layer group alpha, which saves us some work
  recursive = separate_groups or separate_layers

  if type(layer) is gimp.GroupLayer and recursive:
    outline_layer_group(image, layer, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer)
    # if we separated layers or groups, outlines are already filled with color, so 
    # we can skip that part
    if type(layer) is gimp.GroupLayer and not separate_layers and not separate_groups:
      group_outline_layer = add_layer_group_bottom(image,layer)
      paint_selection(group_outline_layer)

  else:
    set_bg_stack(color)

    create_selection(image, layer, thickness, feather)
    outline_layer = add_layer_below(image, layer)
    paint_selection(outline_layer)

    restore_bg_stack()
    
    if merge_source_layer:
      name = layer.name         # save name of original layer
      merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
      merged_layer.name = name  # restore name of original layer
    
  # clear selection and restore background color
  clear_selection(image)

def test_auto():
   img = gimp.image_list()[0]
   test_outline(img, img.active_layer, True, True, False, '#000000', 3, 0, False, True, False)
   print("outline tested")

def gimp_outline_cmdline(color, thickness, feather, separate_mode = 0, merge_source_layer = False):
   img = gimp.image_list()[0]
   test_outline(img, img.active_layer, False, False, False, color, thickness, feather, separate_mode == 1, separate_mode == 2, merge_source_layer)

# def gimp_outline(color, thickness, feather, separate_mode, merge_source_layer, auto, inherit_auto_config, use_defaults):
def gimp_outline(image, drawable, color, thickness, feather, separate_mode, merge_source_layer, auto, inherit_auto_config, use_defaults):
  separate_groups = separate_mode == 1
  separate_layers = separate_mode == 2

  test_outline(image, None, auto, inherit_auto_config, use_defaults, color, thickness, feather, separate_groups, separate_layers, merge_source_layer)


register (
  "gimp-outline",                                          # procedure name for whatever
  "Create outline",                                        # blurb
  "Generate outline of the current layer or layer group.", # help message
  "Tamius Han", "Tamius Han", "2020",                      # author, copyright, year
  "Create outline",                                        # menu name
  "RGBA GRAYA",                                            # type of images we accept
  [                                                        # Parameters
    (PF_IMAGE, "image", "takes current image", None),
    (PF_DRAWABLE, "drawable", "Input layer", None),
    (PF_COLOR, "color", "Outline color", (0,0,0)),
    (PF_INT, "thickness", "Outline thickness", 3),
    (PF_INT, "feather", "Feather", 0),
    (PF_RADIO, "separate_mode", "Outline options", 0, 
      (
        # ("Outline_layer_group on a single layer. Do not outline layers or nested layer groups individually", 0)
        # ("Separate outline for every layer group (outlines from nested layer group are excluded from outline of parent layer group), do not outline layers individually", 1),
        # ("Separate outline for every layer, do not outline layer groups.", 2)
        ("Outline group", 0),
        ("Recurse, outline groups", 1),
        ("Recurse, outline layers", 2)
      )
    ),
    (PF_BOOL, "merge_source_layer", "Merge outline with source layer", False),
    (PF_BOOL, "auto", "Automatic mode (only on layer groups + recursive outline options)", False),
    (PF_BOOL, "inherit_auto_config", "(Automatic-only) Nested layers and layer group inherit settings of their parent", False),
    (PF_BOOL, "use_defaults", "(Automatic-only) do not skip layer groups without configuration block", False)
  ],
  [],                                                      # output / return parameters
  gimp_outline,                                            # python function that will be called
  menu="<Image>/Filters/Decor"
)

main()
