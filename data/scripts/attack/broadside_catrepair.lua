-- Cataclysm-HWRM: the Processor's repair approach (install_base.py repair_order). Its repair beams point straight out
-- of its sides (Repair0-3), so it turns its side to the target (stock broadside: facingAngle 90) and holds off near
-- the beams' range instead of closing in; it only flies after a target once it is well out of range.

function DegToRad(angle)
	return angle * ((2.0*3.141592653589)/360.0)
end

AttackStyleName = FaceTarget

Data =
{
	howToBreakFormation = StraightAndScatter,

-- stop this far out (x the RepairCommand range) and turn its side to the target
	inRangeFactor		= 0.75,
-- slide round keeping the heading until the target is this far out (x the range), then fly to catch up
	slideDistanceMultiplier = 1.1,

	tooSlowSpeed		= 3.0,
	tooFastMultiplier	= 1.4,
	facingAngle		= 90,
	tooLongOutOfRange	= 2.0,

	moveAttackMaxDistanceMultiplier = 1.2,

	tryToMatchHeight = 1,
	tryToGetAboveTarget = 0,

	flyToTargetBecauseItsFarOutOfRangeDelay = 0.5,
	flyToTargetBecauseItsMovingAwayDelay = 2.0,
	stopAndFaceTheTargetDelay = 0.5,
	flyToAboveTheTargetDelay = 4.0,

	strikeGroupFacingPolicy = "TargetFacing",

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
