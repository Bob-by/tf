
from panda3d.core import *
from panda3d.pphysics import *

from tf.tfbase.TFGlobals import Contents
from tf.tfbase.SurfaceProperties import SurfaceProperties

from direct.directbase import DirectRender

from .GameMode import GameMode

class DistributedGameBase:

    def __init__(self):
        self.levelName = ""
        self.lvl = None
        self.lvlData = None
        self.propRoot = None
        self.propPhysRoot = None
        self.gameMode = GameMode.Arena

    def flatten(self, np):
        # Does a flatten even stronger than NodePath.flattenStrong()
        gr = SceneGraphReducer()
        gr.applyAttribs(np.node())
        gr.flatten(np.node(), ~0)
        gr.makeCompatibleState(np.node())
        gr.collectVertexData(np.node(), 0)
        gr.unify(np.node(), False)
        gr.removeUnusedVertices(np.node())

    def processPropGeomNode(self, node, sprop):
        hasAny = False

        tmp = NodePath("tmp")
        tmp.setShaderInput("bakedVertexLight", LVecBase2i(0))

        arrFmt = GeomVertexArrayFormat()
        arrFmt.addColumn(InternalName.make("vertex_lighting"), 3, GeomEnums.NTFloat16, GeomEnums.COther)
        arrFmt = GeomVertexArrayFormat.registerFormat(arrFmt)

        for i in range(node.getNumGeoms()):
            array = sprop.getVertexLighting(self.geomIndex)
            geom = node.getGeom(i)
            vdata = geom.getVertexData()

            if array and (array.getNumRows() == vdata.getNumRows()):
                state = node.getGeomState(i)

                arrIndex = vdata.getNumArrays()
                fmt = vdata.getFormat()

                newFmt = GeomVertexFormat(fmt)
                newFmt.addArray(arrFmt)
                newFmt = GeomVertexFormat.registerFormat(newFmt)

                #print(newFmt)

                newVData = GeomVertexData(vdata)
                newVData.setFormat(newFmt)
                newVData.setArray(arrIndex, array)

                ngeom = geom.makeCopy()
                ngeom.setVertexData(newVData)
                node.setGeom(i, ngeom)

                node.setGeomState(i, state.compose(tmp.getState()))

                hasAny = True

            self.geomIndex += 1
        return hasAny

    def r_processPropNode(self, node, sprop):
        hasAny = False
        if node.isGeomNode():
            hasAny = self.processPropGeomNode(node, sprop)

        for i in range(node.getNumChildren()):
            if self.r_processPropNode(node.getChild(i), sprop):
                hasAny = True
        return hasAny

    def loadLevelProps(self):
        # Create a dedicated DynamicVisNode for culling static props.
        # We have one node dedicated to culling static props and another
        # for dynamic entities (which is base.dynRender).  The reason for
        # this is to reduce the overhead of recomputing the bounding volume
        # of base.dynRender.  If static props and dynamic entities are
        # parented to the same node, we have a lot more nodes to union.
        # And since static props never move, that would be a waste.

        tree = self.lvlData.getAreaClusterTree()

        propRoot = base.render.attachNewNode(StaticPartitionedObjectNode("props"))
        self.propRoot = propRoot
        propRoot.showThrough(DirectRender.ShadowCameraBitmask)
        propPhysRoot = NodePath("propPhysRoot")
        propPhysRoot.hide()
        lightNodes = []

        # We keep track of the models that we loaded so we can evict them
        # from the ModelPoolc ache after we are done.
        # Prop models are typically only loaded one during level loads
        # and fully manipulated after, we so can free up memory by not
        # having them in the cache.
        loadedModels = []

        for i in range(self.lvlData.getNumStaticProps()):
            sprop = self.lvlData.getStaticProp(i)

            if not sprop.getModelFilename().getBasenameWoExtension():
                continue

            modelFilename = sprop.getModelFilename()
            propModel = loader.loadModel(modelFilename, okMissing=True)
            if not propModel or propModel.isEmpty():
                continue

            loadedModels.append(propModel.node())

            if sprop.getSkin() < propModel.node().getNumMaterialGroups():
                propModel.node().setActiveMaterialGroup(sprop.getSkin())

            propModel.setPos(sprop.getPos())
            propModel.setHpr(sprop.getHpr())

            pos = sprop.getPos()

            cnode = None
            cinfo = propModel.node().getCollisionInfo()
            if sprop.getSolid() and cinfo and cinfo.getPart(0).mesh_data:
                part = cinfo.getPart(0)
                if part.concave:
                    mdata = PhysTriangleMeshData(part.mesh_data)
                else:
                    mdata = PhysConvexMeshData(part.mesh_data)
                if mdata.generateMesh():
                    if part.concave:
                        mesh = PhysTriangleMesh(mdata)
                    else:
                        mesh = PhysConvexMesh(mdata)

                    surfaceProp = "default"
                    cdata = propModel.node().getCustomData()
                    if cdata:
                        if cdata.hasAttribute("surfaceprop"):
                            surfaceProp = cdata.getAttributeValue("surfaceprop").getString().lower()
                    sp = SurfaceProperties.get(surfaceProp)
                    if not sp:
                        sp = SurfaceProperties['default']
                    mat = sp.getPhysMaterial()

                    shape = PhysShape(mesh, mat)
                    cnode = PhysRigidStaticNode("propcoll")
                    cnode.addShape(shape)
                    #cnode.setCcdEnabled(True)
                    cnode.addToScene(base.physicsWorld)
                    cnp = propPhysRoot.attachNewNode(cnode)
                    cnp.setTransform(NodePath(), propModel.getTransform(NodePath()))
                    cnode.setContentsMask(Contents.Solid)
                    #cnode.setPythonTag("entity", base.world)

            propModel.flattenLight()
            lodNode = propModel.find("**/+LODNode")
            if not lodNode.isEmpty():
                # Grab the first LOD and throw away the rest so we can flatten.
                propModel = lodNode.getChild(0)

            # Tack on baked per-vertex lighting.
            self.geomIndex = 0
            hasAnyVtxLight = self.r_processPropNode(propModel.node(), sprop)
            #print(hasAnyVtxLight)

            propModel.flattenStrong()

            if propModel.getNumChildren() == 1:
                # If there's just one GeomNode under the ModelRoot, we can throw
                # away the model root.
                propModel = propModel.getChild(0)

            propModel.reparentTo(propRoot)
            in3DSky = False
            if IS_CLIENT:
                # If the prop is positioned in the 3-D skybox, it needs to be
                # parented into the 3-D skybox scene graph.
                leaf = tree.getLeafValueFromPoint(pos)
                if leaf >= 0:
                    pvs = self.lvlData.getClusterPvs(leaf)
                    if pvs.is3dSkyCluster():
                        propModel.reparentTo(base.sky3DRoot)
                        in3DSky = True

                #propModel.setEffect(MapLightingEffect.make(DirectRender.MainCameraBitmask))
                lightNodes.append((propModel, hasAnyVtxLight))

            propModel.node().setFinal(True)
            if not in3DSky:
                propModel.showThrough(DirectRender.ShadowCameraBitmask)

            if cnode:
                cnode.syncTransform()

        #self.flatten(propRoot)

        for propModel, hasVtxLight in lightNodes:
            # Also, we can flatten better by pre-computing the lighting state once.
            lightEffect = MapLightingEffect.make(DirectRender.MainCameraBitmask)
            lightEffect.computeLighting(propModel.getNetTransform(), self.lvlData,
                                        propModel.getBounds(), propModel.getParent().getNetTransform(), hasVtxLight)
            state = propModel.getState()
            state = state.compose(lightEffect.getCurrentLightingState())
            propModel.setState(state)
            propModel.flattenLight()

        # Attempt to share vertex buffers and combine GeomPrimitives
        # across the prop GeomNodes, without actually combining the
        # GeomNodes themselves, so we can cull them effectively.
        propGr = SceneGraphReducer()
        propGr.applyAttribs(propRoot.node())
        propGr.makeCompatibleState(propRoot.node())
        propGr.collectVertexData(propRoot.node(), 0)
        propGr.unify(propRoot.node(), False)
        propGr.removeUnusedVertices(propRoot.node())

        for child in propRoot.getChildren():
            propRoot.node().addObject(child.node())
        propRoot.node().removeAllChildren()

        propRoot.node().partitionObjects(self.lvlData.getNumClusters(), self.lvlData.getAreaClusterTree())

        self.propPhysRoot = propPhysRoot

        # Now evict the prop models we loaded from the ModelPool cache.
        for mdlNode in loadedModels:
            ModelPool.releaseModel(mdlNode)

    def delete(self):
        self.unloadLevel()

    def unloadLevel(self):
        if self.propRoot:
            self.propRoot.removeNode()
            self.propRoot = None
        if self.lvl:
            self.lvl.removeNode()
            self.lvl = None
        self.lvlData = None
        self.levelName = None

    def preFlattenLevel(self):
        pass

    def changeLevel(self, lvlName):
        self.unloadLevel()

        self.levelName = lvlName

        # Don't RAM or disk cache the level BAM file.
        opts = LoaderOptions(LoaderOptions.LFSearch |
                             LoaderOptions.LFReportErrors |
                             LoaderOptions.LFNoCache)
        self.lvl = loader.loadModel(lvlName, loaderOptions=opts)
        #self.lvl.reparentTo(base.render)
        lvlRoot = self.lvl.find("**/+MapRoot")
        lvlRoot.setLightOff(-1)
        data = lvlRoot.node().getData()
        self.lvlData = data

        # Make sure all the RAM copies of lightmaps and cube maps get thrown away when they
        # get uploaded to the graphics card.  They take up a lot of memory.
        for tex in self.lvl.findAllTextures():
            tex.setKeepRamImage(False)
        for i in range(self.lvlData.getNumCubeMaps()):
            mcm = self.lvlData.getCubeMap(i)
            tex = mcm.getTexture()
            if tex:
                tex.setKeepRamImage(False)
                tex.setMinfilter(SamplerState.FTLinear)
                tex.setMagfilter(SamplerState.FTLinear)
                tex.clearRamMipmapImages()

        dummyRoot = PandaNode("mapRoot")
        dummyRoot.replaceNode(lvlRoot.node())

        for i in range(self.lvlData.getNumModels()):
            mdl = self.lvlData.getModel(i)
            gn = mdl.getGeomNode()
            for i in reversed(range(gn.getNumGeoms())):
                geom = gn.getGeom(i)
                state = gn.getGeomState(i)
                if state.hasAttrib(MaterialAttrib):
                    mattr = state.getAttrib(MaterialAttrib)
                    mat = mattr.getMaterial()
                    if mat and isinstance(mat, SkyBoxMaterial):
                        gn.removeGeom(i)

        self.preFlattenLevel()

        self.loadLevelProps()

        self.propPhysRoot.reparentTo(self.lvl)

        #self.lvl.ls()
