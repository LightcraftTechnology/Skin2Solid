bl_info = {
    "name": "Skin2Solid",
    "author": "Mansur Şamil Güngör",
    "version": (1, 0, 2),
    "blender": (4, 0, 0),
    "location": "View3D > UI > Skin2Solid",
    "description": "An add-on to convert skinned mesh animation to object transform animation.",
    "warning": "",
    "wiki_url": "",
    "category": "Animation",
}

import bpy
import bmesh


def separate_mesh_by_vertex_groups(mesh_obj):
    """
    Separate the mesh object by its vertex groups using bmesh and retain the vertex group.
    
    Parameters:
        mesh_obj (bpy.types.Object): A mesh object to separate by vertex groups.
    """
    settings = bpy.context.scene.skin2solid_settings

    # Ensure the object is a mesh
    if mesh_obj.type != 'MESH':
        print("The provided object is not a mesh!")
        return
    
    if settings.objs_collection_created is None:
        return

    # Get vertex group indices and weights for each vertex in the original mesh
    vertex_group_data = []
    for vert in mesh_obj.data.vertices:
        group_data = [(group.group, group.weight) for group in vert.groups]
        vertex_group_data.append(group_data)
    
    # Duplicate the mesh object for each vertex group and keep only the respective group's vertices
    for a, group in enumerate(mesh_obj.vertex_groups):
        # Duplicate the original object
        duplicate = mesh_obj.copy()
        duplicate.data = duplicate.data.copy()
        settings.objs_collection_created.objects.link(duplicate)
        
        bm = bmesh.new()
        bm.from_mesh(duplicate.data)

        to_delete = []
        
        # Check vertices against the vertex group data
        for i, v in enumerate(bm.verts):
            groups_for_vertex = vertex_group_data[i]

            vert_groups_of_vertex = [g for g, w in groups_for_vertex if g == group.index]

            if len(vert_groups_of_vertex) == 0:
                to_delete.append(v)
            
            for vert_group in groups_for_vertex:
                if vert_group[0] == group.index and vert_group[1] < settings.weight_threshold:
                    to_delete.append(v)
                    break

        # Delete unwanted vertices
        bmesh.ops.delete(bm, geom=to_delete, context='VERTS')
        
        # Update the mesh from bmesh and free it
        bm.to_mesh(duplicate.data)
        bm.free()

        # Rename the separated object
        duplicate.name = f"{mesh_obj.name}_{group.name}".replace(settings.name_suffix, "") + settings.name_suffix
        duplicate.data.name = duplicate.name

        # Keep or create only the relevant vertex group
        existing_vg_names = [vg.name for vg in duplicate.vertex_groups]
        if group.name in existing_vg_names:
            for vg in duplicate.vertex_groups:
                if vg.name != group.name:
                    duplicate.vertex_groups.remove(vg)
        else:
            duplicate.vertex_groups.new(name=group.name)
    
    # Remove the original object
    settings.objs_collection_created.objects.unlink(mesh_obj)
    bpy.data.objects.remove(mesh_obj)


def set_rig_to_rest_pose(rig):
    """
    Set the rig to its rest pose.
    
    Parameters:
        rig (bpy.types.Object): The rig to set to its rest pose.
    """
    
    # Ensure the object is an armature
    if rig.type != 'ARMATURE':
        print("The provided object is not an armature!")
        return
    
    # Set the pose to rest
    bpy.data.armatures["Armature"].pose_position = 'REST'


def clear_object_modifiers():
    """
    Clear all modifiers on the active object.
    """
    
    settings = bpy.context.scene.skin2solid_settings
    objs_collection_created = settings.objs_collection_created

    # Ensure the collection is set
    if not objs_collection_created:
        print("Collection not set!")
        return

    for obj in objs_collection_created.objects:
        if obj.type != 'MESH':
            continue
        
        # Clear all modifiers
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE':
                obj.modifiers.remove(mod)


def parent_objects_to_corresponding_bones():
    """
    Parent the objects to the corresponding bones.
    """
    
    settings = bpy.context.scene.skin2solid_settings
    objs_collection_created = settings.objs_collection_created
    rig = settings.rig

    # Parent the objects to the corresponding bones
    for obj in objs_collection_created.objects:
        if obj.type != 'MESH':
            continue
        
        if len(obj.vertex_groups) == 0:
            continue

        # Get the bone name from the vertex group name
        bone_name = obj.vertex_groups[0].name

        if bone_name not in rig.pose.bones:
            continue

        # Set the mode to object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Select the object and the rig and go into pose mode
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        # Clear parent and keep transform
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

        # Select the rig and go into pose mode
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')

        # Select the bone
        rig.data.bones.active = rig.data.bones[bone_name]

        # Parent the object to the bone
        bpy.ops.object.parent_set(type='BONE', keep_transform=True)

    bpy.ops.object.mode_set(mode='OBJECT')
    rig.data.pose_position = 'POSE'


def should_object_be_processed(obj):
    """
    Check if the object should be processed.
    
    Parameters:
        obj (bpy.types.Object): The object to check.
    
    Returns:
        bool: True if the object should be processed, False otherwise.
    """
    settings = bpy.context.scene.skin2solid_settings

    if not settings.rig:
        return False
    
    if obj.type != 'MESH':
        return False
    
    if len(obj.vertex_groups) == 0:
        return False

    has_correct_armature_modifier = False
    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object == settings.rig:
            has_correct_armature_modifier = True
            break
    if not has_correct_armature_modifier:
        return False
    
    return True


def create_new_collection(name):
    """
    Create a new collection with the provided name.
    
    Parameters:
        name (str): The name of the new collection.
    
    Returns:
        bpy.types.Collection: The new collection.
    """
    
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def create_working_collection():
    """
    Create a new collection for the working objects.
    
    Returns:
        bpy.types.Collection: The new collection.
    """
    
    settings = bpy.context.scene.skin2solid_settings
    objs_collection_original = settings.objs_collection_original

    # Ensure the collection is set
    if not objs_collection_original:
        print("Collection not set!")
        return

    # Create a new collection for the working objects
    collection = create_new_collection(f"{objs_collection_original.name}{settings.name_suffix}")

    for obj in objs_collection_original.objects:
        if not should_object_be_processed(obj):
            continue
        bpy.context.view_layer.objects.active = obj
        
        # Duplicate the object and link to the new collection
        duplicate = obj.copy()
        duplicate.name = obj.name + settings.name_suffix
        duplicate.data = obj.data.copy()
        duplicate.data.name = obj.data.name + settings.name_suffix
        collection.objects.link(duplicate)
    
    settings.objs_collection_created = collection
    return collection


def set_object_origins_to_center():
    settings = bpy.context.scene.skin2solid_settings

    if not settings.objs_collection_created:
        return
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    for obj in settings.objs_collection_created.objects:
        if obj.type != "MESH":
            continue
        bpy.ops.object.select_all(action='DESELECT')

        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME')


def prepare_objects():
    """
    Prepare the objects for skinning.
    """
    
    settings = bpy.context.scene.skin2solid_settings
    objs_collection_original = settings.objs_collection_original
    rig = settings.rig

    # Ensure the collection is set
    if not objs_collection_original:
        print("Collection not set!")
        return

    # Ensure the rig is set
    if not rig:
        print("Rig not set! Please select a rig object first.")
        return
    
    # Create a new collection for the working objects
    objs_collection_created = create_working_collection()

    # Separate objects with multiple vertex groups
    for obj in objs_collection_created.objects:
        if obj.type != 'MESH':
            continue
        
        if len(obj.vertex_groups) > 1:
            separate_mesh_by_vertex_groups(obj)

    # Set the rig to rest pose
    set_rig_to_rest_pose(rig)

    # Clear all modifiers
    clear_object_modifiers()

    set_object_origins_to_center()

    # Parent the objects to the corresponding bones
    parent_objects_to_corresponding_bones()

    settings.is_objects_prepared = True


def bake_animation():
    """
    Bake the animation.
    """
    
    settings = bpy.context.scene.skin2solid_settings
    objs_collection_created = settings.objs_collection_created

    # Ensure the collection is set
    if not objs_collection_created:
        print("Collection not set!")
        return

    if bpy.context.view_layer.objects.active is None:
        if len(objs_collection_created.objects) == 0:
            return
        bpy.context.view_layer.objects.active = objs_collection_created.objects[0]

    # Set the mode to object mode
    bpy.ops.object.mode_set(mode='OBJECT')

    # Select the rig and go into pose mode
    bpy.ops.object.select_all(action='DESELECT')
    
    for obj in objs_collection_created.objects:
        if obj.type != 'MESH':
            continue
        
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

    # Bake the animation
    bpy.ops.nla.bake(frame_start=settings.bake_frame_start, frame_end=settings.bake_frame_end, only_selected=True, visual_keying=True, clear_constraints=True, clear_parents=True, bake_types={'OBJECT'})


def verify_operator(operator, check_preparation=False):
    settings = bpy.context.scene.skin2solid_settings

    if not settings.objs_collection_original:
        operator.report({'ERROR'}, "Collection not set! Please select a collection first.")
        return False
    if not settings.rig:
        operator.report({'ERROR'}, "Rig not set! Please select a rig object first.")
        return False
    if check_preparation and not settings.is_objects_prepared:
        operator.report({'ERROR'}, "Objects aren't prepared! Please run the 'Prepare Objects' operator first. ")
        return False
    return True


def update_property(self, context):
    settings = context.scene.skin2solid_settings
    settings.is_objects_prepared = False


class Skin2SolidSettings(bpy.types.PropertyGroup):
    objs_collection_original: bpy.props.PointerProperty(
        type=bpy.types.Collection, 
        name="Objects Collection", 
        update=update_property,
        description="The collection containing the objects to be converted to solid objects"
    )
    objs_collection_created: bpy.props.PointerProperty(
        type=bpy.types.Collection, 
        name="Objects Created",
        update=update_property,
        description="The collection containing the created solid objects"
    )
    rig: bpy.props.PointerProperty(
        type=bpy.types.Object, 
        name="Rig", 
        update=update_property,
        description="The rig object to be used for skinning"
    )
    is_objects_prepared: bpy.props.BoolProperty(name="Is Objects Prepared", default=False)
    bake_frame_start: bpy.props.IntProperty(
        name="Bake Frame Start", 
        default=0,
        min=0,
        description="The start frame for baking the animation"
    )
    bake_frame_end: bpy.props.IntProperty(
        name="Bake Frame End", 
        default=250,
        min=1,
        description="The end frame for baking the animation"
    )
    name_suffix: bpy.props.StringProperty(name="Name Suffix", default="_Solid")
    weight_threshold: bpy.props.FloatProperty(
        name="Weight Threshold", 
        default=0.3,
        description="The minimum weight for a vertex to be included while separating the mesh by vertex groups"
    )


class SKIN2SOLID_OT_separate_by_vertex_groups(bpy.types.Operator):
    """Separate the mesh object by its vertex groups using bmesh."""
    bl_idname = "skin2solid.separate_by_vertex_groups"
    bl_label = "Separate by Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if not verify_operator(self):
            return {'CANCELLED'}

        separate_mesh_by_vertex_groups(context.active_object)
        return {'FINISHED'}


class SKIN2SOLID_OT_prepare_objects(bpy.types.Operator):
    bl_idname = "skin2solid.prepare_objects"
    bl_label = "Prepare Objects"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Duplicate the objects and separate them by vertex groups"
    
    def execute(self, context):
        if not verify_operator(self, False):
            return {'CANCELLED'}
        prepare_objects()
        return {'FINISHED'}


class SKIN2SOLID_OT_bake_animation(bpy.types.Operator):
    bl_idname = "skin2solid.bake_animation"
    bl_label = "Prepare Objects"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Bake the animations and remove the parents of the objects"
    
    def execute(self, context):
        if not verify_operator(self, True):
            return {'CANCELLED'}
        bake_animation()
        return {'FINISHED'}


class SKIN2SOLID_PT_main_panel(bpy.types.Panel):
    bl_label = "Skin2Solid"
    bl_idname = "SKIN2SOLID_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Skin2Solid"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.skin2solid_settings

        box = layout.box()
        col0 = box.column(align=True)

        box1 = col0.box()
        col = box1.column(align=True)
        col.label(text="Objects Collection:")
        col.prop(settings, "objs_collection_original", text="")

        box1 = col0.box()
        col = box1.column(align=True)
        col.label(text="Rig:")
        col.prop(settings, "rig", text="")

        box = layout.box()
        col = box.column(align=True)

        box1 = col.box()
        col1 = box1.column(align=True)
        col1.prop(settings, "weight_threshold", text="Weight Min")
        col1.operator("skin2solid.prepare_objects", text="Prepare Objects", icon="MOD_BUILD")

        box1 = col.box()
        col1 = box1.column(align=True)
        col1.prop(settings, "bake_frame_start", text="Frame Start")
        col1.prop(settings, "bake_frame_end", text="Frame End")
        col1.operator("skin2solid.bake_animation", text="Bake Animation", icon="ARMATURE_DATA")


classes = (
    Skin2SolidSettings,
    SKIN2SOLID_OT_separate_by_vertex_groups,
    SKIN2SOLID_OT_bake_animation,
    SKIN2SOLID_OT_prepare_objects,
    SKIN2SOLID_PT_main_panel
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.skin2solid_settings = bpy.props.PointerProperty(type=Skin2SolidSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.skin2solid_settings


if __name__ == "__main__":
    register()
