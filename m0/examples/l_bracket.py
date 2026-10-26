PARAMS = {"width": 40.0, "height": 30.0, "depth": 20.0, "thickness": 4.0, "hole_d": 5.0, "fillet": 2.0}

p = PARAMS
result = (
    cq.Workplane("XZ")
    .polyline([(0, 0), (p["width"], 0), (p["width"], p["thickness"]),
               (p["thickness"], p["thickness"]), (p["thickness"], p["height"]), (0, p["height"])])
    .close()
    .extrude(-p["depth"])
    .edges("|Y and >X").fillet(p["fillet"] / 2)
    .faces("<Z").workplane(centerOption="CenterOfBoundBox")
    .center(p["width"] / 4, 0).hole(p["hole_d"])
)
