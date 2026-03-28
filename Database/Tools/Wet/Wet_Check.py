import re
import os

class WetLabValidator:
    def __init__(self):
        # Strict validation based on MLD.md
        # Files are valid if they match specific naming conventions for their type.
        pass

    def validate_filename_strict(self, filename, exp_type):
        """
        Validates a filename against the specific rules for the experiment type.
        Returns check_result (bool).
        """
        if filename.startswith("~$") or filename == "Thumbs.db": return False
        
        name, ext = os.path.splitext(filename)
        ext = ext.lower()

        def _is_xth_time(value):
            return bool(re.match(r"^\d+(?:st|nd|rd|th)_Time$", value, re.IGNORECASE))
        
        # --- 1. e Experiment ---
        if exp_type == 'e':
            # spcFiles: Name_Solvent_e_Concentration_MarkerX_BatchTestTime
            # e.g. 5107_DMSO_e_10UM_2_3.spc
            # MarkerX can be number or 'Blank'. BatchTestTime is optional (default 1).
            if ext == '.spc':
                return bool(re.match(r"^.+?_.+?_e_.+?_(?:Blank|\d+)(?:_\d+)?$", name, re.IGNORECASE))
            
            # xlsxFiles: Origin or Working
            # e.g. 5107_DMSO_e_Origin.xlsx, 5107_DMSO_e_Working.xlsx
            if ext == '.xlsx':
                return bool(re.match(r"^.+?_.+?_e_(Origin|Working)$", name, re.IGNORECASE))
                
            # SData (prism, png, md): Name_Solvent_e_Xth_Time_Year_MonthDay
            # e.g. 5107_DMSO_e_1st_Time_2025_1226
            if ext in ['.prism', '.png', '.jpg', '.jpeg', '.md']:
                return bool(re.match(r"^.+?_.+?_e_\d+(?:st|nd|rd|th)_Time_\d{4}_\d{4}$", name, re.IGNORECASE))

        # --- 2. FluoStable (FluorescenceStability) ---
        elif exp_type in ['FluoStable', 'FluorescenceStability']:
            # tmcFiles: Name_Solvent_FluoStable_Con_MarkerX_BatchTestTime
            if ext == '.tmc':
                return bool(re.match(r"^.+?_.+?_Fluo(?:rescence)?(?:Stable|Stability)_.+?_\d+(?:_\d+)?$", name, re.IGNORECASE))
            
            # xlsxFiles: Origin or Working
            if ext == '.xlsx':
                return bool(re.match(r"^.+?_.+?_Fluo(?:rescence)?(?:Stable|Stability)_(Origin|Working)$", name, re.IGNORECASE))
            
            # SData
            if ext in ['.prism', '.png', '.jpg', '.jpeg', '.md']:
                return bool(re.match(r"^.+?_.+?_Fluo(?:rescence)?(?:Stable|Stability)_\d+(?:st|nd|rd|th)_Time_\d{4}_\d{4}$", name, re.IGNORECASE))

        # --- 3. MTT ---
        elif exp_type == 'MTT':
            # xlsxFiles: Origin, Working, Ref
            # e.g. 5107_SY5Y_MTT_Origin, 5107_SY5Y_MTT_Working
            if ext == '.xlsx':
                return bool(re.match(r"^.+?_.+?_MTT_(Origin|Working|Ref)$", name, re.IGNORECASE))
            
            # SData
            if ext in ['.prism', '.png', '.jpg', '.jpeg', '.md']:
                return bool(re.match(r"^.+?_.+?_MTT_\d+(?:st|nd|rd|th)_Time_\d{4}_\d{4}(?:_Ref)?$", name, re.IGNORECASE))

        # --- 4. UVStable (UVStability) ---
        elif exp_type in ['UVStable', 'UVStability']:
            # spcFiles: Name_Solvent_UVStable_Conc_Xth_Time_Loop_Xtimes_Xmin_Year_MonthDay
            if ext == '.spc':
                return bool(re.match(r"^.+?_.+?_UV(?:Stable|Stability)_.+?_\d+(?:st|nd|rd|th)_Time_Loop_\d+times_\d+min_\d{4}_\d{4}$", name, re.IGNORECASE))
            
            # xlsxFiles: Origin, Working
            if ext == '.xlsx':
                return bool(re.match(r"^.+?_.+?_UV(?:Stable|Stability)_.+?_\d+(?:st|nd|rd|th)_Time_Loop_\d+times_\d+min_\d{4}_\d{4}_(Origin|Working)$", name, re.IGNORECASE))
            
            # mdFiles: parameter notes in RData; naming is flexible
            if ext == '.md':
                return True
            
            # SData (prism, opju, png)
            if ext in ['.prism', '.opju', '.png', '.jpg', '.jpeg']:
                return bool(re.match(r"^.+?_.+?_UV(?:Stable|Stability)_.+?_\d+(?:st|nd|rd|th)_Time_\d{4}_?\d{4}$", name, re.IGNORECASE))

        # --- 5. SelectiveI (SelectiveIonic) ---
        elif exp_type in ['SelectiveI', 'SelectiveIonic']:
            # spcFiles: Name_Solvent_SelectiveI_Conc_X(Probe)/X(Protein)_Disrupt_MakerX_BatchTestTime
            if ext == '.spc':
                pattern_basic = r"^.+?_.+?_SelectiveI(?:onic)?_.+?_.+?_(?:Blank|\d+)(?:_\d+)?$"
                return bool(re.match(pattern_basic, name, re.IGNORECASE))
            
            # xlsxFiles: Origin, Working
            if ext == '.xlsx':
                return bool(re.match(r"^.+?_.+?_SelectiveI(?:onic)?_.+?_.+?_(Origin|Working)$", name, re.IGNORECASE))
            
            # mdFiles: parameter notes in RData; naming is flexible
            if ext == '.md':
                return True
            
            # SData (prism, opju, png)
            if ext in ['.prism', '.opju', '.png', '.jpg', '.jpeg']:
                return bool(re.match(r"^.+?_.+?_SelectiveI(?:onic)?_.+?_.+?_\d+(?:st|nd|rd|th)_Time_\d{4}_\d{4}$", name, re.IGNORECASE))
                
        # --- 6. SolventsCom (SolventsComplete) ---
        elif exp_type in ['SolventsCom', 'SolventsComplete', 'SolventsCheck']:
             # Fluo spc: SolventCode+ExSlit+EmSlit+MarkerX+EM/EX (no underscores)
             # SolventCode: ET|MO|PB|EA|MC|DM|DC|HO; Slit: A-F; Marker: digit or T; EM/EX
             # e.g. DCBB1EM.spc
             if ext == '.spc':
                 # Fluo spc format: SolventCode+ExSlit+EmSlit+MarkerX+EM/EX+XthTime
                 # XthTime is a natural number; omit when equal to 1
                 fluo_pattern = r"^(?:ET|MO|PB|EA|MC|DM|DC|HO)[A-F][A-F](?:\d+|T)(?:EM|EX)(?:\d+)?$"
                 if re.match(fluo_pattern, name, re.IGNORECASE):
                     return True
                 # UV spc format: Name_Solvent_Conc_MarkerX_TestTime
                 # e.g. A11_DMSO_10UM_1_2
                 uv_pattern = r"^.+?_.+?_.+?_(?:Blank|\d+)(?:_\d+)?$"
                 return bool(re.match(uv_pattern, name, re.IGNORECASE))
             
             if ext == '.xlsx':
                 # Origin/Working: Name_SolventsCom_Fluo/UV_Origin/Working
                 # Fin: Name_SolventsCom_Fin
                 return bool(re.match(r"^.+?_Solvents?(?:Com|Complete|Check)_(?:Fluo|UV)_(Origin|Working)$", name, re.IGNORECASE)) or \
                        bool(re.match(r"^.+?_Solvents?(?:Com|Complete|Check)_Fin$", name, re.IGNORECASE))
             
             # Files in Pics folders are accepted directly by db_indexer.
             # This is a fallback to accept image files if they appear here.
             
             if ext == '.md':
                 # mdFiles: Name_SolventsCom (parameter notes in RData)
                 # Or in SData: Name_SolventsCom_Fin/FluoEm/FluoEx/UV
                 return bool(re.match(r"^.+?_Solvents?(?:Com|Complete|Check)(?:_(?:Fin|FluoEm|FluoEx|UV))?$", name, re.IGNORECASE))
             
             if ext in ['.prism', '.opju', '.png', '.jpg', '.jpeg']:
                 # SData: Name_SolventsCom_Fin/FluoEm/FluoEx/UV
                 return bool(re.match(r"^.+?_Solvents?(?:Com|Complete|Check)_(?:Fin|FluoEm|FluoEx|UV)$", name, re.IGNORECASE))

        # --- 7. Confocal1mage / Confal1mage ---
        elif exp_type in ['Confocal1mage', 'Confal1mage']:
            if ext == '.lif':
                return bool(re.match(r"^.+?_Conf(?:ocal|al)1mage_\d+(?:st|nd|rd|th)_Time_(Origin|Working)$", name, re.IGNORECASE))
            if ext == '.md':
                return bool(re.match(r"^.+?_Conf(?:ocal|al)1mage_\d+(?:st|nd|rd|th)_Time$", name, re.IGNORECASE))
            if ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
                # SData: CellLine_Function_PositionX_DyeName (DyeName can include underscores)
                return bool(re.match(r"^.+?_.+?_Position\d+_.+$", name, re.IGNORECASE))

        # --- 8. IF-P --- (accept all, no naming checks)
        elif exp_type == 'IF-P':
            return True

        return False


class FolderParser:
    """
    Parses folder names based on My Lab Data (MLD) naming conventions.
    """
    @staticmethod
    def parse(folder_name):
        # 1. Determine Experiment Type and Dispatch
        if "_e_" in folder_name: return FolderParser.parse_e(folder_name)
        
        # Support both 'FluorescenceStability' and 'FluoStable'
        if "_FluorescenceStability_" in folder_name or "_FluoStable_" in folder_name: 
            return FolderParser.parse_fluo_stable(folder_name)
            
        if "_MTT_" in folder_name: return FolderParser.parse_mtt(folder_name)
        
        # Support 'UVStability' and 'UVStable'
        if "_UVStability_" in folder_name or "_UVStable_" in folder_name: 
            return FolderParser.parse_uv_stable(folder_name)
            
        # Support 'SelectiveIonic' and 'SelectiveI'
        if "_SelectiveIonic_" in folder_name or "_SelectiveI_" in folder_name: 
            return FolderParser.parse_selective_i(folder_name)

        # Support Confocal1mage / Confal1mage
        if "_Confocal1mage_" in folder_name or "_Confal1mage_" in folder_name:
            return FolderParser.parse_confocal_image(folder_name)

        # Support IF-P
        if "_IF-P_" in folder_name:
            return FolderParser.parse_if_p(folder_name)
            
        # Support 'SolventsComplete' and 'SolventsCom'
        if "_SolventsComplete_" in folder_name or "_SolventsCom_" in folder_name: 
            return FolderParser.parse_solvents_com(folder_name, 'SolventsCom')

        # Support 'SolventsCheck'
        if "_SolventsCheck_" in folder_name: 
            return FolderParser.parse_solvents_com(folder_name, 'SolventsCheck')
            
        return None

    @staticmethod
    def _create_result(exp_type, match, folder_name):
        data = match.groupdict()
        data['exp_type'] = exp_type
        data['batch_name'] = folder_name
        
        # Handle Status/Mark
        if data.get('mark'):
            raw_mark = (data['mark'] or '').strip().lower()
            status_map = {
                'undone': 'UnDone',
                'unvaluable': 'UnValuable',
                'test': 'Test'
            }
            data['status'] = status_map.get(raw_mark, data['mark'])
        else:
            data['status'] = 'Normal'
            
        # Rename 'date' to 'date_str' for DB compatibility
        if 'date' in data:
            data['date_str'] = data['date']
        else:
            data['date_str'] = ''
            
        # Ensure common fields exist
        for key in ['solvent', 'conc', 'round', 'probe']:
            if key not in data:
                data[key] = ''

        # --- Enhanced Display Fields (User Request) ---
        # 1. Format Experiment Type (e.g. 'e' -> 'e', 'FluoStable' -> 'FluoStable')
        # Using the exp_type passed in is usually fine, but user wanted "e" specifically shown.
        data['exp_type_display'] = exp_type
        
        # Strip whitespace from string fields to avoids UI matching issues
        data['molecule'] = (data.get('molecule') or '').strip()
        data['solvent'] = (data.get('solvent') or '').strip()
        if 'conc' in data: data['conc'] = (data.get('conc') or '').strip()
        if 'probe' in data: data['probe'] = (data.get('probe') or '').strip()
        
        # Matches logic in app.py
        data['round_display'] = (data.get('round') or '').strip()
        raw_round = data['round_display']
        if raw_round:
            # If it ends with _Time, strip it. Case insensitive
            if raw_round.lower().endswith('_time'):
                data['round_display'] = raw_round[:-5] # remove _Time
            # If it matches digit+st/nd/rd/th (optional common case)
            elif re.match(r'^\d+(st|nd|rd|th)$', raw_round, re.IGNORECASE):
                data['round_display'] = raw_round
        
        return data

    @staticmethod
    def parse_e(name):
        # Preferred: Name_Solvent_e_Xth_Time_Year_MonthDay_Mark (with solvent)
        pattern_with_solvent = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_e_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_solvent, name, re.IGNORECASE)
        if match: return FolderParser._create_result('e', match, name)
        
        # Generic rule: Name_e_Xth_Time_Year_MonthDay_Mark (without solvent)
        pattern_no_solvent = r"^(?P<molecule>.+?)_e_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_solvent, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('e', match2, name)
        
        return None

    @staticmethod
    def parse_fluo_stable(name):
        # Preferred: Name_Solvent_FluoStable_Xth_Time_Year_MonthDay_Mark (with solvent)
        pattern_with_solvent = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_Fluo(?:rescence)?(?:Stable|Stability)_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_solvent, name, re.IGNORECASE)
        if match: return FolderParser._create_result('FluoStable', match, name)
        
        # Generic rule: Name_FluoStable_Xth_Time_Year_MonthDay_Mark (without solvent)
        pattern_no_solvent = r"^(?P<molecule>.+?)_Fluo(?:rescence)?(?:Stable|Stability)_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_solvent, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('FluoStable', match2, name)
        return None

    @staticmethod
    def parse_mtt(name):
        # Preferred: Name_CellLine_MTT_Xth_Time_Year_MonthDay_Mark (with CellLine)
        pattern_with_cl = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_MTT_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_cl, name, re.IGNORECASE)
        if match: return FolderParser._create_result('MTT', match, name)
        
        # Generic rule: Name_MTT_Xth_Time_Year_MonthDay_Mark (without CellLine)
        pattern_no_cl = r"^(?P<molecule>.+?)_MTT_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_cl, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('MTT', match2, name)
        return None

    @staticmethod
    def parse_uv_stable(name):
        # Detailed with concentration: Name_Solvent_UVStable_Conc_Xth_Time... (strict and preferred)
        pattern_detail = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_UV(?:Stable|Stability)_(?P<conc>.+?)_(?P<round>\d+(?:st|nd|rd|th)_Time)(?:_.+?)?_(?P<date>\d{4}_?\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match3 = re.match(pattern_detail, name, re.IGNORECASE)
        if match3: return FolderParser._create_result('UVStable', match3, name)
        
        # Compatible: Name_Solvent_UVStable_Xth_Time_Year_MonthDay_Mark (with solvent)
        pattern_with_solvent = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_UV(?:Stable|Stability)_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_?\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_with_solvent, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('UVStable', match2, name)
        
        # Generic rule: Name_UVStable_Xth_Time_Year_MonthDay_Mark (without solvent)
        pattern_no_solvent = r"^(?P<molecule>.+?)_UV(?:Stable|Stability)_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_?\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_no_solvent, name, re.IGNORECASE)
        if match: return FolderParser._create_result('UVStable', match, name)
        
        return None

    @staticmethod
    def parse_selective_i(name):
        # Detailed: Name_Solvent_SelectiveI_Conc_Probe_Xth_Time... (strict and preferred)
        pattern_detail = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_SelectiveI(?:onic)?_(?P<conc>.+?)_(?P<probe>.+?)_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match3 = re.match(pattern_detail, name, re.IGNORECASE)
        if match3: return FolderParser._create_result('SelectiveI', match3, name)
        
        # Compatible: Name_Solvent_SelectiveI_Xth_Time_Year_MonthDay_Mark (with solvent)
        pattern_with_solvent = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_SelectiveI(?:onic)?_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_with_solvent, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('SelectiveI', match2, name)
        
        # Generic rule: Name_SelectiveI_Xth_Time_Year_MonthDay_Mark (without solvent)
        pattern_no_solvent = r"^(?P<molecule>.+?)_SelectiveI(?:onic)?_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_no_solvent, name, re.IGNORECASE)
        if match: return FolderParser._create_result('SelectiveI', match, name)
        
        return None

    @staticmethod
    def parse_solvents_com(name, type_name):
        # Support both:
        # 1) Name_Solvent_SolventsCom_Xth_Time_Year_MonthDay[_Mark]
        # 2) Name_SolventsCom_Xth_Time_Year_MonthDay[_Mark]
        pattern_with_solvent = r"^(?P<molecule>.+?)_(?P<solvent>.+?)_" + re.escape(type_name) + r"_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_solvent, name, re.IGNORECASE)
        if match: return FolderParser._create_result(type_name, match, name)

        pattern_no_solvent = r"^(?P<molecule>.+?)_" + re.escape(type_name) + r"_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_solvent, name, re.IGNORECASE)
        if match2: return FolderParser._create_result(type_name, match2, name)
        return None

    @staticmethod
    def parse_confocal_image(name):
        # Generic rule: Name_Confal1mage_Xth_Time_Year_MonthDay_Mark (with date)
        pattern_with_date = r"^(?P<molecule>.+?)_Conf(?:ocal|al)1mage_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_date, name, re.IGNORECASE)
        if match: return FolderParser._create_result('Confocal1mage', match, name)
        
        # Compatible: Name_Confal1mage_Xth_Time_Mark (without date)
        pattern_no_date = r"^(?P<molecule>.+?)_Conf(?:ocal|al)1mage_(?P<round>\d+(?:st|nd|rd|th)_Time)(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_date, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('Confocal1mage', match2, name)
        return None

    @staticmethod
    def parse_if_p(name):
        # Generic rule: Name_IF-P_Xth_Time_Year_MonthDay_Mark (with date)
        pattern_with_date = r"^(?P<molecule>.+?)_IF-P_(?P<round>\d+(?:st|nd|rd|th)_Time)_(?P<date>\d{4}_\d{4})(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match = re.match(pattern_with_date, name, re.IGNORECASE)
        if match: return FolderParser._create_result('IF-P', match, name)
        
        # Compatible: Name_IF-P_Xth_Time_Mark (without date)
        pattern_no_date = r"^(?P<molecule>.+?)_IF-P_(?P<round>\d+(?:st|nd|rd|th)_Time)(?:_(?P<mark>UnDone|UnValuable|Test))?$"
        match2 = re.match(pattern_no_date, name, re.IGNORECASE)
        if match2: return FolderParser._create_result('IF-P', match2, name)
        return None

validator = WetLabValidator()
