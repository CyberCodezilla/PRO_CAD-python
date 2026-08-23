"""
STEP Exporter — ISO 10303-21 Physical File Format Exporter.
Serves as a robust faceted boundary representation (FACETED_BREP) fallback
for exporting 3D meshes to STEP AP203/AP214 when analytical OpenCASCADE kernels are bypassed.
"""

from datetime import datetime, timezone
from typing import List, Tuple, Any
import numpy as np


class StepExporter:
    """Faceted STEP (ISO 10303-21) physical file writer"""

    @staticmethod
    def export_mesh_to_step(vertices: np.ndarray, faces: np.ndarray, part_name: str = "PART_SOLID") -> str:
        """
        Convert triangular mesh into an ISO 10303-21 STEP physical file containing
        MANIFOLD_SOLID_BREP / FACETED_BREP topology.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        lines = []

        # ISO-10303-21 Header Section
        lines.append("ISO-10303-21;")
        lines.append("HEADER;")
        lines.append(f"FILE_DESCRIPTION(('Python CAD Pro 3D Solid Model'),'2;1');")
        lines.append(f"FILE_NAME('{part_name}.step','{timestamp}',('CAD Pro Engineer'),('CAD Pro Systems'),'Python CAD Pro ISO-10303 AP214 Engine','Python CAD Pro','Approved');")
        lines.append("FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));")
        lines.append("ENDSEC;")
        lines.append("DATA;")

        eid = 1
        # Context & Organization Entities
        lines.append(f"#{eid} = APPLICATION_CONTEXT('core data for automotive mechanical design processes');")
        app_ctx_id = eid; eid += 1
        lines.append(f"#{eid} = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#{app_ctx_id});"); eid += 1
        lines.append(f"#{eid} = PRODUCT_CONTEXT('',#{app_ctx_id},'mechanical');")
        prod_ctx_id = eid; eid += 1
        lines.append(f"#{eid} = PRODUCT('{part_name}','{part_name}','', ( #{prod_ctx_id} ) );")
        prod_id = eid; eid += 1
        lines.append(f"#{eid} = PRODUCT_DEFINITION_FORMATION('1.0', '', #{prod_id});")
        pdf_id = eid; eid += 1
        lines.append(f"#{eid} = PRODUCT_DEFINITION_CONTEXT('part definition', #{app_ctx_id}, 'design');")
        pdc_id = eid; eid += 1
        lines.append(f"#{eid} = PRODUCT_DEFINITION('{part_name}', '', #{pdf_id}, #{pdc_id});")
        pd_id = eid; eid += 1

        # Coordinate System & Geometric Context
        lines.append(f"#{eid} = CARTESIAN_POINT('', ( 0.0, 0.0, 0.0 ) );")
        origin_id = eid; eid += 1
        lines.append(f"#{eid} = DIRECTION('', ( 0.0, 0.0, 1.0 ) );")
        dir_z_id = eid; eid += 1
        lines.append(f"#{eid} = DIRECTION('', ( 1.0, 0.0, 0.0 ) );")
        dir_x_id = eid; eid += 1
        lines.append(f"#{eid} = AXIS2_PLACEMENT_3D('', #{origin_id}, #{dir_z_id}, #{dir_x_id});")
        axis_id = eid; eid += 1

        # Write Cartesian Points for vertices
        vertex_point_ids = []
        for v in vertices:
            lines.append(f"#{eid} = CARTESIAN_POINT('', ( {v[0]:.6f}, {v[1]:.6f}, {v[2]:.6f} ) );")
            vertex_point_ids.append(eid)
            eid += 1

        # Write Faceted Faces
        face_ids = []
        for f in faces:
            p1_id, p2_id, p3_id = vertex_point_ids[f[0]], vertex_point_ids[f[1]], vertex_point_ids[f[2]]
            
            # Polyloop for triangle
            lines.append(f"#{eid} = POLY_LOOP('', ( #{p1_id}, #{p2_id}, #{p3_id} ) );")
            loop_id = eid; eid += 1
            
            lines.append(f"#{eid} = FACE_OUTER_BOUND('', #{loop_id}, .T.);")
            bound_id = eid; eid += 1
            
            lines.append(f"#{eid} = FACETED_BREP_SHAPE_REPRESENTATION('', ( #{bound_id} ), #{axis_id});")
            # Plane normal calculation
            v0 = vertices[f[0]]
            v1 = vertices[f[1]]
            v2 = vertices[f[2]]
            n = np.cross(v1 - v0, v2 - v0)
            norm = np.linalg.norm(n)
            if norm > 1e-9:
                n = n / norm
            else:
                n = np.array([0.0, 0.0, 1.0])
                
            lines.append(f"#{eid} = DIRECTION('', ( {n[0]:.6f}, {n[1]:.6f}, {n[2]:.6f} ) );")
            norm_dir_id = eid; eid += 1
            lines.append(f"#{eid} = AXIS2_PLACEMENT_3D('', #{p1_id}, #{norm_dir_id}, #{dir_x_id});")
            face_axis_id = eid; eid += 1
            lines.append(f"#{eid} = PLANE('', #{face_axis_id});")
            plane_id = eid; eid += 1
            lines.append(f"#{eid} = ADVANCED_FACE('', ( #{bound_id} ), #{plane_id}, .T.);")
            face_ids.append(eid)
            eid += 1

        # Closed Shell and Manifold Solid B-Rep
        faces_str = ", ".join([f"#{fid}" for fid in face_ids])
        lines.append(f"#{eid} = CLOSED_SHELL('', ( {faces_str} ) );")
        shell_id = eid; eid += 1
        lines.append(f"#{eid} = MANIFOLD_SOLID_BREP('{part_name}', #{shell_id});")
        solid_id = eid; eid += 1

        # Shape Representation Context
        lines.append(f"#{eid} = ( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(( #{eid+1} )) GLOBAL_UNIT_ASSIGNED_CONTEXT(( #{eid+2}, #{eid+3}, #{eid+4} )) REPRESENTATION_CONTEXT('Context #1', '3D Context with UNIT and UNCERTAINTY') );")
        rep_ctx_id = eid; eid += 1
        lines.append(f"#{eid} = UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-05), #{eid+1}, 'DISTANCE_ACCURACY_VALUE', 'Confusion accuracy');"); eid += 1
        lines.append(f"#{eid} = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI., .METRE.) );"); eid += 1
        lines.append(f"#{eid} = ( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($, .RADIAN.) );"); eid += 1
        lines.append(f"#{eid} = ( NAMED_UNIT(*) SOLID_ANGLE_UNIT() SI_UNIT($, .STERADIAN.) );"); eid += 1

        lines.append(f"#{eid} = ADVANCED_BREP_SHAPE_REPRESENTATION('{part_name}', ( #{solid_id}, #{axis_id} ), #{rep_ctx_id});")
        shape_rep_id = eid; eid += 1
        lines.append(f"#{eid} = PRODUCT_DEFINITION_SHAPE('','', #{pd_id});")
        pds_id = eid; eid += 1
        lines.append(f"#{eid} = SHAPE_DEFINITION_REPRESENTATION(#{pds_id}, #{shape_rep_id});")

        lines.append("ENDSEC;")
        lines.append("END-ISO-10303-21;")

        return "\n".join(lines)
