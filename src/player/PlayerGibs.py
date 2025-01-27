from panda3d.core import *
from panda3d.pphysics import *

from tf.tfbase.SurfaceProperties import SurfaceProperties
from tf.tfbase.TFGlobals import Contents, CollisionGroup
from tf.actor.Model import Model

from direct.directbase import DirectRender
from direct.interval.IntervalGlobal import Sequence, Wait, Func, LerpColorScaleInterval, Parallel

import random

gibForceUp = 1.0
gibForce = 350.0

class PlayerGibs:

    def __init__(self, pos, hpr, skin, gibInfo):
        self.gibs = []
        self.headPiece = None

        for i in range(len(gibInfo)):
            partInfo = gibInfo.get(i).getElement()
            mdlFilename = partInfo.getAttributeValue("model").getString()
            isHead = False
            if partInfo.hasAttribute("is_head"):
                isHead = partInfo.getAttributeValue("is_head").getBool()
            mdl = Model()
            mdl.setSkin(skin)
            if not mdl.loadModel(mdlFilename):
                mdl.cleanup()
                continue

            mdl.modelNp.setTransparency(True)

            surfaceProp = "default"
            customData = mdl.modelData
            if customData is not None:
                if customData.hasAttribute("surfaceprop"):
                    surfaceProp = customData.getAttributeValue("surfaceprop").getString()
            surfaceDef = SurfaceProperties.get(surfaceProp)
            if not surfaceDef:
                continue

            # Setup physics for giblet piece.
            cinfo = mdl.modelRootNode.getCollisionInfo()
            cpart = cinfo.getPart(0)
            if cpart.concave:
                cmdata = PhysTriangleMeshData(cpart.mesh_data)
                cmesh = PhysTriangleMesh(cmdata)
            else:
                cmdata = PhysConvexMeshData(cpart.mesh_data)
                cmesh = PhysConvexMesh(cmdata)
            cshape = PhysShape(cmesh, surfaceDef.getPhysMaterial())
            cnode = PhysRigidDynamicNode("gib-%i" % i)
            cnode.addShape(cshape)
            cnode.computeMassProperties()
            cnode.setMass(cpart.mass)
            cnode.setLinearDamping(cpart.damping)
            cnode.setAngularDamping(cpart.rot_damping)
            cnode.setCollisionGroup(CollisionGroup.Gibs)
            cnode.setContentsMask(Contents.Solid)
            cnode.setSolidMask(Contents.Solid)
            cnode.setCcdEnabled(True)
            cnode.addToScene(base.physicsWorld)
            cnp = base.dynRender.attachNewNode(cnode)
            cnp.node().setFinal(True)
            cnp.setPos(pos)
            cnp.setHpr(hpr)
            cnp.setEffect(MapLightingEffect.make(DirectRender.MainCameraBitmask))
            cnp.showThrough(DirectRender.ShadowCameraBitmask)
            cnode.syncTransform()
            mdl.modelNp.reparentTo(cnp)

            partVel = Vec3.up()
            partVel.x += random.uniform(-1.0, 1.0)
            partVel.y += random.uniform(-1.0, 1.0)
            partVel.z += random.uniform(0.0, 1.0)
            partVel.normalize()
            partVel *= gibForce

            #cnode.setLinearVelocity(partVel)

            #print(partVel)

            angImpulse = Vec3(random.uniform(0, 120.0), random.uniform(0, 120.0), 0)
            #cnode.setAngularVelocity(angImpulse)

            cnode.addForce(partVel, cnode.FTVelocityChange)
            cnode.addTorque(angImpulse, cnode.FTVelocityChange)

            if isHead:
                self.headPiece = cnp

            self.gibs.append((cnp, mdl))

        # Fade gibs out after 10 seconds.
        self.track = Sequence(Wait(10.0))
        fadeTrack = Parallel()
        for _, mdl in self.gibs:
            fadeTrack.append(LerpColorScaleInterval(mdl.modelNp, 0.75, (1, 1, 1, 0), (1, 1, 1, 1)))
        self.track.append(fadeTrack)
        self.track.append(Func(self.destroy))
        self.track.start()

    def getHeadPosition(self):
        # Return the world-space COM of the head gib.
        return self.headPiece.getMat(base.render).xformPoint(self.headPiece.node().getCenterOfMass())

    def getHeadMatrix(self):
        # Returns the transform matrix of the world-space COM of the head gib.
        return self.headPiece.getMat(base.render) * LMatrix4.translateMat(self.headPiece.node().getCenterOfMass())

    def destroy(self):
        if self.track:
            self.track.finish()
            self.track = None
        if self.gibs:
            for gib, mdl in self.gibs:
                mdl.cleanup()
                gib.node().removeFromScene(base.physicsWorld)
                gib.removeNode()
            self.gibs = None
        self.headPiece = None
