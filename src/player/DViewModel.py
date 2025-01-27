
from tf.actor.DistributedChar import DistributedChar

from .DViewModelShared import DViewModelShared

from panda3d.core import *

class ViewInfo:
    pass

class BobState:

    def __init__(self):
        self.bobTime = 0.0
        self.lastBobTime = 0.0
        self.lastSpeed = 0.0
        self.verticalBob = 0.0
        self.lateralBob = 0.0

cl_wpn_sway_interp = 0.1
cl_wpn_sway_scale = 5.0

class DViewModel(DistributedChar, DViewModelShared):

    def __init__(self):
        DistributedChar.__init__(self)
        DViewModelShared.__init__(self)
        self.lastFacing = Vec3()
        self.bobState = BobState()
        self.lagAngles = Quat()
        self.ivLagAngles = InterpolatedQuat()
        self.ivLagAngles.setInterpolationAmount(cl_wpn_sway_interp)

        self.removeInterpolatedVar(self.ivPos)
        self.removeInterpolatedVar(self.ivRot)

    def resetSway(self):
        """
        Clears the sway interpolation history so that an abrupt change/override
        of view angles doesn't cause weird artifacts.
        """
        self.ivLagAngles.clearHistory()

    def addPredictionFields(self):
        DistributedChar.addPredictionFields(self)
        # We shouldn't attempt to predict the view model transform.
        # Neither the server nor client simulate it, and the view is
        # setup before rendering.
        self.removePredictionField("pos")
        self.removePredictionField("hpr")

    def shouldSpatializeAnimEventSounds(self):
        return (self != base.localAvatar.viewModel)

    def RecvProxy_pos(self, x, y, z):
        pass

    def RecvProxy_rot(self, r, i, j, k):
        pass

    def RecvProxy_scale(self, sx, sy, sz):
        pass

    def calcView(self, player, camera):
        """
        Main rountine to calculate the position and orientation of the view
        model.  Follows the camera, but applies bob, lag, and sway.
        """

        info = ViewInfo()
        info.originalAngles = camera.getQuat()
        info.angles = camera.getQuat()
        info.origin = camera.getPos()

        if self.player:
            wpn = self.player.getActiveWeaponObj()
            if wpn:
                # Add weapon-specific bob.
                wpn.addViewModelBob(self, info)

        # Add model-specific bob even if no weapon associated (for head bob for off hand models)
        self.addViewModelBob(player, info)
        # Add lag.
        self.calcViewModelLag(info)

        self.setPos(info.origin)
        self.setQuat(info.angles)

        #print("vm view is", info.origin, info.angles.getHpr())

    def addViewModelBob(self, player, info):
        pass

    def calcViewModelLag(self, info):
        self.calcViewModelLag_TF(info)

    def calcViewModelLag_TF(self, info):
        """
        tf_viewmodel lag
        """

        if cl_wpn_sway_interp <= 0.0:
            return

        # Calculate our drift
        forward = info.angles.getForward()
        right = info.angles.getRight()
        up = info.angles.getUp()

        # Add an entry to the history.
        self.ivLagAngles.recordValue(info.angles, globalClock.frame_time, False)

        # Interpolate back 100 ms.
        self.ivLagAngles.interpolate(globalClock.frame_time)

        lagAngles = self.ivLagAngles.getInterpolatedValue()

        # Now take the 100ms angle difference and figure out how far the forward vector
        # moved in local space.
        invAngles = Quat()
        invAngles.invertFrom(info.angles)
        angleDiff = lagAngles * invAngles
        laggedForward = angleDiff.getForward()
        forwardDiff = laggedForward - Vec3.forward()
        forwardDiff *= cl_wpn_sway_scale

        # Now offset the origin using that
        info.origin += forward * forwardDiff[1] + right * forwardDiff[0] + up * forwardDiff[2]

    def calcViewModelLag_HL2(self, info):
        """
        baseviewmodel lag
        """
        origPos = Vec3(info.origin)
        origAng = Quat(info.angles)

        maxViewModelLag = 1.5

        # calculate our drift
        forward = info.angles.getForward()

        if globalClock.dt != 0.0:
            difference = forward - self.lastFacing

            speed = 5.0

            diff = difference.length()
            if (diff > maxViewModelLag) and (maxViewModelLag > 0.0):
                scale = diff / maxViewModelLag
                speed *= scale

            self.lastFacing += difference * (speed * globalClock.dt)
            self.lastFacing.normalize()
            info.origin += difference * -5.0

        forward = origAng.getForward()
        right = origAng.getRight()
        up = origAng.getUp()
        hpr = origAng.getHpr()

        pitch = hpr[1]
        if (pitch > 180.0):
            pitch -= 360
        elif (pitch < -180.0):
            pitch += 360

        if maxViewModelLag == 0.0:
            info.origin = origPos
            info.angles = origAng

        info.origin += forward * (-pitch * 0.035)
        info.origin += right * (-pitch * 0.03)
        info.origin += up * (-pitch * 0.02)

    def __playerPoll(self, task):
        if self.playerId != -1 and self.player is None:
            # Poll for the player.
            if self.updatePlayer():
                return task.done
        return task.cont

    def shouldPredict(self):
        if self.playerId == base.localAvatarId:
            return True
        return DistributedChar.shouldPredict(self)

    def announceGenerate(self):
        DistributedChar.announceGenerate(self)
        self.addTask(self.__playerPoll, "vmPlayerPoll", sort=31, appendTask=True, sim=True)

    def disable(self):
        if self.player:
            self.player.viewModel = None
            self.player = None
        if hasattr(base, 'localAvatarId'):
            if self.playerId == base.localAvatarId:
                self.reparentTo(hidden)
        DistributedChar.disable(self)

    def updatePlayer(self):
        self.player = base.cr.doId2do.get(self.playerId)
        if self.player:
            self.player.viewModel = self
        if self.playerId == base.localAvatarId:
            self.reparentTo(base.vmRender)
        else:
            self.reparentTo(base.hidden)

        return self.player

    def RecvProxy_playerId(self, playerId):
        changed = playerId != self.playerId
        self.playerId = playerId
        if changed:
            self.updatePlayer()
