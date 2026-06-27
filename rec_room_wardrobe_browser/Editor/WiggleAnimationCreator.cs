using UnityEngine;
using UnityEditor;
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;

public class FaceAnimator : EditorWindow
{
    private string rootPath = "Assets/faceassets";
    private float frameRate = 6f;
    private Transform faceRoot;

    private string MaterialsPath => Path.Combine(rootPath, "Materials").Replace('\\', '/');

    private const string ShaderName = "VRChat/Mobile/Particles/Multiply";

    [MenuItem("OldBean SDK/Wiggle Animation Creator")]
    public static void ShowWindow()
    {
        GetWindow<FaceAnimator>("Face Animation Parser");
    }

    private void OnGUI()
    {
        GUILayout.Label("Paths", EditorStyles.boldLabel);
        rootPath = EditorGUILayout.TextField("Root Folder", rootPath);

        EditorGUILayout.Space();
        GUILayout.Label("Resolved Subpaths", EditorStyles.miniLabel);
        EditorGUI.BeginDisabledGroup(true);
        EditorGUILayout.TextField("  Idle Mode", Path.Combine(rootPath, "idle").Replace('\\', '/'));
        EditorGUILayout.TextField("  Talk Mode", Path.Combine(rootPath, "talk").Replace('\\', '/'));
        EditorGUILayout.TextField("  Materials", MaterialsPath);
        EditorGUI.EndDisabledGroup();

        EditorGUILayout.Space();
        GUILayout.Label("Settings", EditorStyles.boldLabel);
        frameRate = EditorGUILayout.FloatField("Frame Rate", frameRate);

        EditorGUILayout.Space();
        GUILayout.Label("Face VRCFury Setup", EditorStyles.boldLabel);
        faceRoot = (Transform)EditorGUILayout.ObjectField("Root Object", faceRoot, typeof(Transform), true);
        EditorGUILayout.HelpBox(
            "After generating animations, automatically finds the 'Face' child and adds:\n" +
            "• VRCFury Toggle — idle clip, on by default, no menu entry\n" +
            "• VRCFury Talking — talk clip plays while avatar speaks\n\n" +
            "Leave Root Object empty to search all scene roots.",
            MessageType.None);

        EditorGUILayout.Space();
        if (GUILayout.Button("Create Animations"))
            CreateAnimations();
    }

    // ── Data Classes ────────────────────────────────────────────────────────────

    [Serializable]
    private class AnimationData
    {
        public AnimationInfo  animation;
        public KeyframeData[] keyframes;
    }

    [Serializable]
    private class AnimationInfo
    {
        public string name;
        public float  frame_rate;
        public int    total_keyframes;
        public int    unique_textures;
    }

    [Serializable]
    private class KeyframeData
    {
        public float  time;
        public string type;
        public int    image_index;
    }

    // ── Main ────────────────────────────────────────────────────────────────────

    private void CreateAnimations()
    {
        EnsureFolder(rootPath);

        bool idleSuccess = ProcessSequence("idle");
        bool talkSuccess = ProcessSequence("talk");

        if (idleSuccess || talkSuccess)
        {
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            // Set up VRCFury components on the Face object using the generated clips
            AnimationClip idleClip = idleSuccess ? AssetDatabase.LoadAssetAtPath<AnimationClip>(
                Path.Combine(rootPath, "idle.anim").Replace('\\', '/')) : null;
            AnimationClip talkClip = talkSuccess ? AssetDatabase.LoadAssetAtPath<AnimationClip>(
                Path.Combine(rootPath, "talk.anim").Replace('\\', '/')) : null;

            SetupFaceVRCFury(idleClip, talkClip);

            EditorUtility.DisplayDialog("Success", $"Finished generating animations in:\n{rootPath}", "OK");
        }
    }

    private bool ProcessSequence(string modeName)
    {
        string modePath     = Path.Combine(rootPath, modeName).Replace('\\', '/');
        string jsonPath     = Path.Combine(modePath, "animation_data.json").Replace('\\', '/');
        string texturesPath = Path.Combine(modePath, "textures").Replace('\\', '/');
        string modelsPath   = Path.Combine(modePath, "models").Replace('\\', '/');

        if (!Directory.Exists(modePath) || !File.Exists(jsonPath) || !Directory.Exists(texturesPath) || !Directory.Exists(modelsPath))
        {
            Debug.LogWarning($"FaceAnimator: Missing necessary files/folders for '{modeName}' mode in {modePath}. Skipping.");
            return false;
        }

        AnimationData animData = LoadJson(jsonPath);
        if (animData == null) return false;

        Dictionary<int, Texture2D> textures = LoadTextures(texturesPath);
        List<Mesh>                 meshes   = LoadMeshes(modelsPath);

        if (textures.Count == 0) { Debug.LogWarning($"FaceAnimator: No textures found for '{modeName}'."); return false; }
        if (meshes.Count == 0)   { Debug.LogWarning($"FaceAnimator: No meshes found for '{modeName}'."); return false; }

        Dictionary<int, Material> materials = BuildMaterials(textures, animData, modeName);
        AnimationClip             clip      = BuildClip(animData, materials, meshes, modeName);

        string clipPath = Path.Combine(rootPath, $"{modeName}.anim").Replace('\\', '/');
        AssetDatabase.CreateAsset(clip, clipPath);

        Debug.Log($"FaceAnimator: Successfully created '{modeName}.anim' with {animData.keyframes.Length} keyframes, {textures.Count} textures, {meshes.Count} meshes.");
        return true;
    }

    // ── Loaders ─────────────────────────────────────────────────────────────────

    private AnimationData LoadJson(string path)
    {
        string json = File.ReadAllText(path);
        AnimationData data = JsonUtility.FromJson<AnimationData>(json);
        if (data == null || data.keyframes == null) return null;
        return data;
    }

    private Dictionary<int, Texture2D> LoadTextures(string path)
    {
        var dict = new Dictionary<int, Texture2D>();
        foreach (string file in Directory.GetFiles(path, "*.png", SearchOption.TopDirectoryOnly))
        {
            string name = Path.GetFileNameWithoutExtension(file);
            if (!int.TryParse(name, out int index)) continue;

            Texture2D tex = AssetDatabase.LoadAssetAtPath<Texture2D>(ToAssetPath(file));
            if (tex != null) dict[index] = tex;
        }
        return dict;
    }

    private List<Mesh> LoadMeshes(string path)
    {
        return AssetDatabase.FindAssets("t:Mesh", new[] { path })
            .Select(guid => AssetDatabase.LoadAssetAtPath<Mesh>(AssetDatabase.GUIDToAssetPath(guid)))
            .Where(m => m != null)
            .OrderBy(m => {
                var match = Regex.Match(m.name, @"var(\d+)");
                return match.Success ? int.Parse(match.Groups[1].Value) : 0;
            })
            .ToList();
    }

    // ── Builders ─────────────────────────────────────────────────────────────────

    private Dictionary<int, Material> BuildMaterials(Dictionary<int, Texture2D> textures, AnimationData animData, string modeName)
    {
        EnsureFolder(MaterialsPath);

        var dict   = new Dictionary<int, Material>();
        var shader = Shader.Find(ShaderName);

        if (shader == null)
        {
            Debug.LogError($"Shader not found: {ShaderName}\nMake sure the VRChat SDK is imported.");
            return dict;
        }

        foreach (int index in animData.keyframes.Select(k => k.image_index).Distinct())
        {
            if (!textures.TryGetValue(index, out Texture2D tex)) continue;

            Material mat = new Material(shader)
            {
                mainTexture = tex,
                name        = $"{modeName}_Mat_{index:00}"
            };

            string matPath = Path.Combine(MaterialsPath, $"{mat.name}.mat").Replace('\\', '/');
            AssetDatabase.CreateAsset(mat, matPath);
            dict[index] = mat;
        }

        return dict;
    }

    private AnimationClip BuildClip(AnimationData animData, Dictionary<int, Material> materials, List<Mesh> meshes, string modeName)
    {
        AnimationClip clip = new AnimationClip
        {
            name      = modeName,
            frameRate = frameRate,
            wrapMode  = WrapMode.Loop
        };

        AnimationClipSettings settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.loopTime = true;
        AnimationUtility.SetAnimationClipSettings(clip, settings);

        float length = animData.keyframes.Max(k => k.time);
        if (length <= 0) length = animData.keyframes.Length / frameRate;

        SetMaterialCurve(clip, animData, materials);
        SetMeshCurve(clip, meshes, length);

        return clip;
    }

    private void SetMaterialCurve(AnimationClip clip, AnimationData animData, Dictionary<int, Material> materials)
    {
        EditorCurveBinding binding = new EditorCurveBinding
        {
            type         = typeof(MeshRenderer),
            path         = "",
            propertyName = "m_Materials.Array.data[0]"
        };

        ObjectReferenceKeyframe[] keys = animData.keyframes
            .Where(kf => materials.ContainsKey(kf.image_index))
            .Select(kf => new ObjectReferenceKeyframe { time = kf.time, value = materials[kf.image_index] })
            .ToArray();

        AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
    }

    private void SetMeshCurve(AnimationClip clip, List<Mesh> meshes, float length)
    {
        EditorCurveBinding binding = new EditorCurveBinding
        {
            type         = typeof(MeshFilter),
            path         = "",
            propertyName = "m_Mesh"
        };

        int totalFrames = Mathf.CeilToInt(length * frameRate);
        var keys        = new ObjectReferenceKeyframe[totalFrames];
        var rng         = new System.Random();
        int lastIndex   = -1;

        for (int frame = 0; frame < totalFrames; frame++)
        {
            int idx;
            do { idx = rng.Next(0, meshes.Count); }
            while (idx == lastIndex && meshes.Count > 1);
            lastIndex = idx;

            keys[frame] = new ObjectReferenceKeyframe { time = frame / frameRate, value = meshes[idx] };
        }

        AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
    }

    // ── Face VRCFury Setup ───────────────────────────────────────────────────────

    private void SetupFaceVRCFury(AnimationClip idleClip, AnimationClip talkClip)
    {
        Type vrcFuryType    = FindType("VF.Model.VRCFury");
        Type toggleType     = FindType("VF.Model.Feature.Toggle");
        Type talkingType    = FindType("VF.Model.Feature.Talking");
        Type stateType      = FindType("VF.Model.State");
        Type clipActionType = FindType("VF.Model.StateAction.AnimationClipAction");
        Type guidClipType   = FindType("VF.Model.GuidAnimationClip");

        if (vrcFuryType == null)
        {
            Debug.LogWarning("[FaceAnimator] VRCFury not found — skipping face VRCFury setup.");
            return;
        }

        GameObject faceObj = FindFaceObject();
        if (faceObj == null)
        {
            Debug.LogWarning("[FaceAnimator] No 'Face' GameObject found in the hierarchy — skipping VRCFury setup.");
            return;
        }

        Undo.SetCurrentGroupName("Setup Face VRCFury");
        int undoGroup = Undo.GetCurrentGroup();

        // Idle toggle — no menu path, on by default
        if (toggleType != null && idleClip != null)
        {
            var fury = Undo.AddComponent(faceObj, vrcFuryType) as Component;
            var toggle = Activator.CreateInstance(toggleType);
            SetField(toggleType, toggle, "name",      "");
            SetField(toggleType, toggle, "defaultOn", true);
            if (stateType != null)
                SetField(toggleType, toggle, "state", BuildState(stateType, clipActionType, guidClipType, idleClip));
            SetField(vrcFuryType, fury, "content", toggle);
            EditorUtility.SetDirty(fury);
        }

        // Talking — plays talk clip while avatar speaks
        if (talkingType != null && talkClip != null)
        {
            var fury = Undo.AddComponent(faceObj, vrcFuryType) as Component;
            var talking = Activator.CreateInstance(talkingType);
            if (stateType != null)
                SetField(talkingType, talking, "state", BuildState(stateType, clipActionType, guidClipType, talkClip));
            SetField(vrcFuryType, fury, "content", talking);
            EditorUtility.SetDirty(fury);
        }

        Undo.CollapseUndoOperations(undoGroup);
        Debug.Log($"[FaceAnimator] VRCFury components added to '{faceObj.name}'.");
    }

    private static object BuildState(Type stateType, Type clipActionType, Type guidClipType, AnimationClip clip)
    {
        var state = Activator.CreateInstance(stateType);
        if (clipActionType == null || guidClipType == null || clip == null) return state;

        var action   = Activator.CreateInstance(clipActionType);
        var guidClip = Activator.CreateInstance(guidClipType);
        SetField(guidClipType, guidClip, "objRef", clip);
        SetField(clipActionType, action, "clip", guidClip);

        var actionsList = GetField(stateType, state, "actions") as IList;
        actionsList?.Add(action);

        return state;
    }

    private GameObject FindFaceObject()
    {
        if (faceRoot != null)
            return FindInHierarchy(faceRoot, "Face");

        foreach (var go in UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects())
        {
            var result = FindInHierarchy(go.transform, "Face");
            if (result != null) return result;
        }
        return null;
    }

    private static GameObject FindInHierarchy(Transform root, string name)
    {
        if (root.name == name) return root.gameObject;
        foreach (Transform child in root)
        {
            var result = FindInHierarchy(child, name);
            if (result != null) return result;
        }
        return null;
    }

    // ── Reflection Helpers ───────────────────────────────────────────────────────

    private static Type FindType(string fullName)
    {
        foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            var t = assembly.GetType(fullName);
            if (t != null) return t;
        }
        return null;
    }

    private static void SetField(Type type, object obj, string fieldName, object value)
    {
        type.GetField(fieldName, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
            ?.SetValue(obj, value);
    }

    private static object GetField(Type type, object obj, string fieldName)
    {
        return type.GetField(fieldName, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                   ?.GetValue(obj);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────────

    private static void EnsureFolder(string path)
    {
        if (AssetDatabase.IsValidFolder(path)) return;

        string parent = Path.GetDirectoryName(path).Replace('\\', '/');
        string folder = Path.GetFileName(path);
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, folder);
    }

    private static string ToAssetPath(string fullPath) =>
        fullPath.Replace(Application.dataPath, "Assets").Replace('\\', '/');
}
