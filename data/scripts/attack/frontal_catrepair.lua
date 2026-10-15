-- Cataclysm-HWRM: the Worker's repair approach (install_base.py repair_order). Stock frontal_supportfrigate, made to
-- hold off near its beam's full range (Cataclysm's Worker repaired from repairDistance, not alongside) and not to
-- chase a target that is still in range: it faces the target and only flies after it once it is well out of range.

function DegToRad(angle)
	return angle * ((2.0*3.141592653589)/360.0)
end

AttackStyleName = FaceTarget

Data =
{
	howToBreakFormation = StraightAndScatter,

-- stop this far out (x the RepairCommand range) and face the target
	inRangeFactor		= 0.8,
-- slide round keeping the heading until the target is this far out (x the range), then fly to catch up
	slideDistanceMultiplier = 1.1,

	tooSlowSpeed		= 3.0,
	tooFastMultiplier	= 1.4,
	facingAngle		= 0,
	tooLongOutOfRange	= 2.0,

	moveAttackMaxDistanceMultiplier = 1.2,

	tryToMatchHeight = 0,
	tryToGetAboveTarget = 0,

	flyToTargetBecauseItsFarOutOfRangeDelay = 0.5,
	flyToTargetBecauseItsMovingAwayDelay = 2.0,
	stopAndFaceTheTargetDelay = 0.5,
	flyToAboveTheTargetDelay = 4.0,

	safeDistanceFromTargetToDoActions = 6.0,
	safeDistanceFromTargetToDoActionsAg = 6.0,
	safeDistanceFromTargetToDoActionsEv = 6.0,

	RandomActions =
	{
		{
			Type = NoAction,
			Weighting = 1,
		},
	},
	BeingAttackedActions =
	{
		{
			Type = NoAction,
			Weighting = 1,
		},
	},
	FiringActions =
	{
		{
			Type = NoAction,
			Weighting = 1,
		},
	},
}
