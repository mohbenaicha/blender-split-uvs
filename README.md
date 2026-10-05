# UV Repack

Gives each mesh its own full UV space. When one model is split into many objects,
they all still share the original UV layout, so every piece uses a tiny corner of
the texture. Select a mesh, open the **N** panel sidebar, and click **Repack UVs**
in the **UV Repack** tab. That mesh's UV islands are rescaled and repacked to fill
its own 0-1 UV tile, while every other object stays untouched.

Typical workflow: split your model (for example `Mesh > Separate > By Loose
Parts`), select each separated object, then click **Repack UVs**.
