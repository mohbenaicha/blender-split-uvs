# UV Repack

Gives each mesh its own full UV space. Splitting a model leaves every object
sharing the original layout, so each piece uses a tiny corner of the texture.
Select a mesh, open the **N** panel sidebar, and click **Repack UVs** under the
**UV Repack** tab: its islands are rescaled and repacked to fill its own 0-1 tile,
leaving other objects untouched.

**Bake Textures** resamples your existing maps (colour, normal, ORM) through the
new UVs, preserving each object's texel density.

Workflow: split your model (`Mesh > Separate > By Loose Parts`), select an object,
click **Repack UVs**, then **Bake Textures**.
