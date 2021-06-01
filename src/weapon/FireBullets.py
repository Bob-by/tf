
from tf.tfbase.TFGlobals import DamageType
from .TakeDamageInfo import *

from panda3d.core import Quat, Vec3

import random

def fireBullets(player, origin, angles, weapon, mode, seed, spread, damage = -1.0, critical = False):
    """
    Fires some bullets.  Server does damage calculations.  Client would
    theoretically do the effects (when I implement it).
    """

    doEffects = False # TODO: true on client!

    q = Quat()
    q.setHpr(angles)
    forward = q.getForward()
    right = q.getRight()
    up = q.getUp()

    weaponData = weapon.weaponData.get(mode, {})

    fireInfo = {}
    fireInfo['src'] = origin
    if damage < 0.0:
        fireInfo['damage'] = weaponData.get('damage', 1.0)
    else:
        fireInfo['damage'] = int(damage)
    fireInfo['distance'] = weaponData.get('range', 1000000)
    fireInfo['shots'] = 1
    fireInfo['spread'] = Vec3(spread, spread, 0.0)
    fireInfo['ammoType'] = 0
    #fireInfo['attacker'] =

    # Setup the bullet damage type
    damageType = weapon.damageType
    customDamageType = -1

    # Reset multi-damage structures.
    clearMultiDamage()

    bulletsPerShot = weaponData.get('bulletsPerShot', 1)
    for i in range(bulletsPerShot):
        random.seed(seed)

        # Get circular gaussian spread.
        x = random.uniform(-0.5, 0.5) + random.uniform(-0.5, 0.5)
        y = random.uniform(-0.5, 0.5) + random.uniform(-0.5, 0.5)

        # Initialize the variable firing information
        fireInfo['dirShooting'] = forward + (right * x * spread) + (up * y * spread)
        fireInfo['dirShooting'].normalize()

        # Fire the bullet!
        player.fireBullet(fireInfo, doEffects, damageType, customDamageType)

        # Use new seed for next bullet.
        seed += 1

    # Reset random seed.
    random.seed(None)

    # Apply damage if any.
    applyMultiDamage()
